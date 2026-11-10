"""Deterministic, public-information heuristics for play with a nonempty deck.

Scores are preferences, not solved game values. Unknown cards are treated as
uniformly distributed; remembered pickups are facts, inferred suit voids aren't.
"""
from math import comb

from durak.utils.cards import DurakCard


class CardMemory:
    """Remember only cards visibly transferred to the opponent by a pickup."""

    def __init__(self):
        self.enemy = set()
        self.table = set()
        self.attacking = False

    def observe(self, phase, table, hand, discarded):
        self.enemy.difference_update(set(table) | hand | discarded)
        self.table = set(table)
        self.attacking = phase != 'respond'

    def played(self, cards):
        self.table.update(cards)

    def deal(self, hand, gamedata):
        if 'discarded' not in gamedata:
            # Without the bout result we cannot distinguish a take from a discard.
            self.enemy.clear()
        else:
            discarded = set(map(DurakCard, gamedata['discarded']))
            if self.attacking:
                self.enemy.update(self.table - discarded)
            self.enemy.difference_update(hand | discarded)
        self.table.clear()
        self.attacking = False


class MiddlegamePolicy:
    def __init__(self, hand, trump, table, gamedata, known_enemy=()):
        self.hand = hand
        self.trump = trump
        self.table = tuple(map(DurakCard, table))
        self.deck_count = gamedata['deck_count']
        self.enemy_count = gamedata['enemy_count']
        discarded = set(map(DurakCard, gamedata['discarded']))
        self.unseen = DurakCard.all() - hand - set(self.table) - discarded
        # The face-up bottom trump stays in the deck until the deck is empty.
        self.possible_enemy = self.unseen - {trump}
        self.known_enemy = set(known_enemy) & self.possible_enemy
        self.unknown = self.possible_enemy - self.known_enemy
        self.unknown_count = self.enemy_count - len(self.known_enemy)
        if not 0 <= self.unknown_count <= len(self.unknown):
            raise ValueError('inconsistent remembered hand')

    @classmethod
    def available(cls, hand, trump, table, gamedata):
        """Legacy protocol clients may omit metadata; keep their old fallback."""
        if not {'deck_count', 'enemy_count', 'discarded'} <= gamedata.keys():
            return False
        deck, enemy = gamedata['deck_count'], gamedata['enemy_count']
        if not isinstance(deck, int) or not isinstance(enemy, int) or deck <= 0 or enemy < 0:
            return False
        table = tuple(map(DurakCard, table))
        discarded = tuple(map(DurakCard, gamedata['discarded']))
        visible = hand | set(table) | set(discarded)
        return (len(visible) == len(hand) + len(table) + len(discarded)
                and len(visible) + deck + enemy == 36 and trump not in visible)

    def probability_has(self, cards):
        """Hypergeometric probability, conditional on certain pickup cards."""
        cards = set(cards)
        if cards & self.known_enemy:
            return 1.0
        hits = len(cards & self.unknown)
        total, count = len(self.unknown), self.unknown_count
        return 1.0 - comb(total - hits, count) / comb(total, count)

    def keep_value(self, card):
        # Count live lower cards: a king whose entire suit has gone is no stopper.
        lower = sum(c.suit == card.suit and c.numeric_rank < card.numeric_rank
                    for c in self.unseen)
        value = 0.35 * card.numeric_rank + 0.10 * lower
        if card.suit == self.trump.suit:
            value += 6.0
        elif lower and not any(c.suit == card.suit and c > card for c in self.hand):
            value += 0.4  # retain the strongest cover in each nontrump suit
        return value

    def attack_evaluation(self, card):
        partners = sum(c.rank == card.rank and c != card
                       and c.suit != self.trump.suit for c in self.hand)
        same_suit = {c for c in self.possible_enemy
                     if c.suit == card.suit and c > card}
        beating = same_suit | {c for c in self.possible_enemy
                              if card.suit != self.trump.suit and c.suit == self.trump.suit}
        in_suit, any_defence = self.probability_has(same_suit), self.probability_has(beating)
        pressure = 0.6 * (1 - in_suit) + 0.6 * (1 - any_defence)
        keep = self.keep_value(card)
        return {'keep_value': keep, 'matching_partners': partners,
                'prob_enemy_beats_in_suit': in_suit, 'prob_enemy_can_beat': any_defence,
                'partner_bonus': 1.2 * partners, 'pressure_bonus': pressure,
                'score': keep - 1.2 * partners - pressure}

    def attack_score(self, card):
        return self.attack_evaluation(card)['score']

    def move(self):
        legal = self.hand.cards_that_can_be_added_to(self.table, including_trumps=not self.table)
        if not legal:
            return ()
        card = min(legal, key=lambda c: (self.attack_score(c), c))
        return (card,)

    def defence_evaluation(self, card):
        ranks = {c.rank for c in self.table}
        matching = {c for c in self.possible_enemy if c.rank == card.rank}
        # Spending one rank higher can prevent another attack. Already exposed
        # ranks do not create an additional opportunity for the opponent.
        exposure = self.probability_has(matching) if card.rank not in ranks else 0.0
        keep = self.keep_value(card)
        return {'keep_value': keep, 'opens_new_rank': card.rank not in ranks,
                'prob_enemy_matching_rank': self.probability_has(matching),
                'exposure_penalty': 1.2 * exposure, 'score': keep + 1.2 * exposure}

    def defence_score(self, card):
        return self.defence_evaluation(card)['score']

    def respond(self):
        legal = self.hand.cards_that_can_beat(self.table[-1])
        if not legal:
            return ()
        card = min(legal, key=lambda c: (self.defence_score(c), c))
        return (card,)

    def give_more(self):
        # Do not hand over trumps voluntarily while the opponent can refill.
        # Cheap matching nontrumps make their pickup larger and free draw slots.
        legal = self.hand.cards_that_can_be_added_to(self.table, including_trumps=False)
        limit = max(0, self.enemy_count - 1)
        return tuple(legal[:limit])

    def explain(self, phase, chosen):
        """Report the actual heuristic, including legal actions it does not score."""
        candidates = []
        if phase == 'respond':
            legal = self.hand.cards_that_can_beat(self.table[-1])
            for card in legal:
                candidates.append({'action': 'play', 'cards': [str(card)], 'evaluated': True,
                                   'selected': card in chosen, **self.defence_evaluation(card)})
            candidates.append({'action': 'take', 'cards': [], 'evaluated': False,
                               'selected': not chosen, 'score': None,
                               'reason': ('Taking is not evaluated when a beating card exists.' if legal
                                          else 'No card can beat the attack.')})
            reason = ('Lowest heuristic cost among beating cards; taking was not evaluated.' if legal
                      else 'No card can beat the attack; take the table.')
        else:
            for card in self.hand.cards_that_can_be_added_to(self.table):
                allowed = card.suit != self.trump.suit or (phase == 'move' and not self.table)
                row = {'action': 'play' if phase == 'move' else 'throw', 'cards': [str(card)],
                       'selected': card in chosen, 'evaluated': allowed and phase == 'move'}
                if allowed and phase == 'move':
                    row.update(self.attack_evaluation(card))
                else:
                    row.update(score=None, reason=('Reserve trumps on optional attacks and throw-ins.'
                                                  if not allowed else 'Lowest nontrumps first, within capacity.'))
                candidates.append(row)
            if self.table or phase == 'give_more':
                candidates.append({'action': 'stop' if phase == 'move' else 'throw', 'cards': [],
                                   'selected': not chosen, 'evaluated': False, 'score': None,
                                   'reason': 'Rule-based continuation; passing is not scored.'})
            reason = ('Lowest heuristic attack cost; reserve trumps on optional continuations.'
                      if phase == 'move' else 'Throw lowest matching nontrumps, within defender capacity.')
        return {'reason': reason, 'score_convention': 'lower is preferred; heuristic costs, not win probabilities',
                'candidates': candidates, 'throw_limit': max(0, self.enemy_count - 1) if phase == 'give_more' else None,
                'belief': {'model': 'uniform unknown cards, conditioned on public cards and certain pickups',
                           'known_enemy': list(map(str, sorted(self.known_enemy))),
                           'possible_enemy': list(map(str, sorted(self.possible_enemy))),
                           'unknown_enemy_count': self.unknown_count,
                           'card_probabilities': {str(c): self.probability_has({c}) for c in sorted(DurakCard.all())},
                           'suit_probabilities': {s: self.probability_has({c for c in self.possible_enemy if c.suit == s})
                                                  for s in DurakCard.SUITS},
                           'rank_probabilities': {r: self.probability_has({c for c in self.possible_enemy if c.rank == r})
                                                  for r in DurakCard.RANKS}}}
