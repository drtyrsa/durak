"""A fast full-game Durak simulator on bit masks, for Monte Carlo rollouts.

Rules follow GameController exactly: draw order, the throw-in limit, the
immediate finish once the deck is empty, and the last-card draw exception.
Bits are ordered by playing value, so the lowest set bit of any hand is its
cheapest card: plain suits rank by rank first, all trumps come last.
"""
from durak.utils.cards import DurakCard

MOVE, RESPOND, GIVE = 0, 1, 2
DRAW = -1  # result of a drawn game; otherwise the winner's seat (0 or 1)
STOPPED = 2  # with stop_at_empty: STOPPED + attacker when the deck runs out


class Universe:
    """Card <-> bit mapping and precomputed rule masks for one trump suit."""

    def __init__(self, trump):
        trump_suit = DurakCard(trump).suit
        plain = [suit for suit in DurakCard.SUITS if suit != trump_suit]
        self.cards = ([DurakCard(rank, suit) for rank in DurakCard.RANKS for suit in plain]
                      + [DurakCard(rank, trump_suit) for rank in DurakCard.RANKS])
        self.bit = {card: 1 << i for i, card in enumerate(self.cards)}
        self.trumps = 0x1FF << 27
        self.plain = (1 << 27) - 1
        self.full = (1 << 36) - 1
        self.rank = [card.numeric_rank for card in self.cards]
        self.rank_mask = []  # index -> all four cards of that rank
        self.beaters = []  # index -> cards beating it
        for card in self.cards:
            self.rank_mask.append(sum(bit for other, bit in self.bit.items()
                                      if other.numeric_rank == card.numeric_rank))
            self.beaters.append(sum(
                bit for other, bit in self.bit.items()
                if (other.suit == card.suit and other.numeric_rank > card.numeric_rank)
                or (other.suit == trump_suit != card.suit)))

    def mask(self, cards):
        mask = 0
        for card in cards:
            mask |= self.bit[DurakCard(card)]
        return mask

    def unpack(self, mask):
        """Cards of a mask, cheapest first."""
        result = []
        while mask:
            low = mask & -mask
            mask ^= low
            result.append(self.cards[low.bit_length() - 1])
        return result

    def ranks(self, table):
        ranks = 0
        while table:
            low = table & -table
            table ^= low
            ranks |= self.rank_mask[low.bit_length() - 1]
        return ranks


def _draw(hands, deck, first):
    for seat in (first, 1 - first):
        if not deck:
            return
        need = 6 - hands[seat].bit_count()
        while need > 0 and deck:
            hands[seat] |= deck.pop()
            need -= 1


def _finished(hands, deck):
    if deck or (hands[0] and hands[1]):
        return None
    if not hands[0] and not hands[1]:
        return DRAW
    return 0 if not hands[0] else 1


def pickup(hands, deck, attacker, table, given=0):
    """Resolve a legal pickup and refill in controller order; mutate both lists.

    The attacker keeps the initiative. Return a terminal result or None.
    Shared by rollouts and pickup reply probes so draw order cannot diverge.
    """
    hands[attacker] ^= given
    hands[1 - attacker] |= table | given
    _draw(hands, deck, 1 - attacker)
    return _finished(hands, deck)


def defence(u, hand, pending, table, deck_count, careful=False):
    """A cheap defence policy using only the defender's hand and public state.

    Selective pickups preserve expensive trumps while the deck is substantial.
    A large table or an already bloated hand makes another pickup unattractive.
    This is a continuation policy, never a restriction on legal root actions.
    """
    choices = hand & u.beaters[pending.bit_length() - 1]
    card = choices & -choices
    if (careful and deck_count > 4 and card & u.trumps
            and (hand | table).bit_count() <= 9 and table.bit_count() <= 3):
        if (u.rank[card.bit_length() - 1] >= 5
                or (table.bit_count() == 1 and u.rank[pending.bit_length() - 1] >= 6)):
            return 0
    return card


def _checked(u, action, hands, attacker, table, pending, mode):
    """Validate an action mask supplied by a rollout policy hook."""
    if not isinstance(action, int) or action < 0:
        raise ValueError('policy hook must return a non-negative int mask or None')
    if mode == MOVE:
        if not action:
            if not table:
                raise ValueError('policy hook: cannot pass with an empty table')
        elif (action & (action - 1) or not hands[attacker] & action
              or table and not u.ranks(table) & action):
            raise ValueError('policy hook: illegal attack')
    elif mode == RESPOND:
        if action and (action & (action - 1) or not hands[1 - attacker] & action
                       or not u.beaters[pending.bit_length() - 1] & action):
            raise ValueError('policy hook: illegal defence')
    elif (action & ~hands[attacker] or action & ~u.ranks(table)
          or action.bit_count() >= hands[1 - attacker].bit_count()):
        raise ValueError('policy hook: illegal throw-ins')
    return action


def rollout(u, hands, deck, attacker, table, pending, mode, forced=None, limit=2000,
            stop_at_empty=False, careful=0, policy=None):
    """Play to the end and return the winner's seat or DRAW.

    ``hands`` is a two-item list of masks and ``deck`` a list of bits whose
    *last* item is drawn first; both are modified. ``table`` holds every card
    in the current bout; ``pending`` is the uncovered attack while responding.
    ``forced`` is the first decision's action (a bit, a mask of throw-ins, or
    0 for stop/take/nothing); after it, both seats play the cheap policy:
    attack and throw in with the cheapest card of a matching rank, saving
    trumps while the deck lasts, and beat with the cheapest card. ``careful``
    is a seat bitmask enabling selective pickups for either simulated player.
    ``policy``, if given, is consulted before the built-in cheap policy on
    every decision that is not ``forced``: it receives the current state
    ``(u, hands, deck, attacker, table, pending, mode)`` and returns an action
    mask, or None to defer to the built-in policy. Its mover is the defender
    in RESPOND mode and the attacker otherwise. Returned actions are
    validated and must be legal.

    With ``stop_at_empty``, play stops at the first bout boundary with an
    empty deck and returns ``STOPPED + attacker``; ``hands`` then holds the
    perfect-information position for an exact solver.
    """
    rank_mask, beaters, plain = u.rank_mask, u.beaters, u.plain
    ranks = u.ranks(table)
    for _ in range(limit):
        defender = 1 - attacker
        if mode == MOVE:
            if forced is not None:
                card, forced = forced, None
            else:
                card = None
                if policy is not None:
                    card = policy(u, hands, deck, attacker, table, pending, MOVE)
                    if card is not None:
                        card = _checked(u, card, hands, attacker, table, pending, MOVE)
                if card is None:
                    own = hands[attacker]
                    if not table:
                        choices = own & plain or own
                    else:
                        choices = own & ranks
                        if deck:
                            choices &= plain
                    card = choices & -choices
            if card:
                hands[attacker] ^= card
                table |= card
                ranks |= rank_mask[card.bit_length() - 1]
                pending, mode = card, RESPOND
                if not deck and not (hands[attacker] and hands[defender]):
                    rest = hands[defender]
                    if not (not hands[attacker] and rest.bit_count() == 1
                            and rest & beaters[card.bit_length() - 1]):
                        return _finished(hands, deck)
            else:  # successful defence: discard, roles swap
                table = ranks = 0
                _draw(hands, deck, attacker)
                attacker, mode = defender, MOVE
                result = _finished(hands, deck)
                if result is not None:
                    return result
                if stop_at_empty and not deck:
                    return STOPPED + attacker
        elif mode == RESPOND:
            if forced is not None:
                card, forced = forced, None
            else:
                card = None
                if policy is not None:
                    card = policy(u, hands, deck, attacker, table, pending, RESPOND)
                    if card is not None:
                        card = _checked(u, card, hands, attacker, table, pending, RESPOND)
                if card is None:
                    card = defence(u, hands[defender], pending, table, len(deck),
                                   careful & (1 << defender))
            if card:
                hands[defender] ^= card
                table |= card
                ranks |= rank_mask[card.bit_length() - 1]
                pending = 0
                if hands[defender] and hands[attacker]:
                    mode = MOVE
                else:
                    table = ranks = 0
                    _draw(hands, deck, attacker)
                    attacker, mode = defender, MOVE
                    result = _finished(hands, deck)
                    if result is not None:
                        return result
                    if stop_at_empty and not deck:
                        return STOPPED + attacker
            elif hands[attacker]:
                mode = GIVE
            else:
                result = pickup(hands, deck, attacker, table)
                table = ranks = 0
                mode = MOVE
                if result is not None:
                    return result
                if stop_at_empty and not deck:
                    return STOPPED + attacker
        else:  # GIVE
            if forced is not None:
                given, forced = forced, None
            else:
                given = None
                if policy is not None:
                    given = policy(u, hands, deck, attacker, table, pending, GIVE)
                    if given is not None:
                        given = _checked(u, given, hands, attacker, table, pending, GIVE)
                if given is None:
                    choices = hands[attacker] & ranks
                    if deck:
                        choices &= plain
                    given = 0
                    for _ in range(hands[defender].bit_count() - 1):
                        if not choices:
                            break
                        low = choices & -choices
                        choices ^= low
                        given |= low
            result = pickup(hands, deck, attacker, table, given)
            table = ranks = 0
            mode = MOVE
            if result is not None:
                return result
            if stop_at_empty and not deck:
                return STOPPED + attacker
    raise RuntimeError('rollout did not finish')
