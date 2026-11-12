"""Public-card memory and analytic bout evaluation outside exact search.

Scores are preferences, not solved game values. Unknown cards are treated as
uniformly distributed; remembered pickups are facts, inferred suit voids aren't.
"""
from math import comb

from durak.engine.exchange import BoutEvaluator
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
        self.possible_enemy = self.unseen - ({trump} if self.deck_count else set())
        self.known_enemy = set(known_enemy) & self.possible_enemy
        self.unknown = self.possible_enemy - self.known_enemy
        self.unknown_count = self.enemy_count - len(self.known_enemy)
        if not 0 <= self.unknown_count <= len(self.unknown):
            raise ValueError('inconsistent remembered hand')
        self._evaluator = BoutEvaluator(self)

    @classmethod
    def available(cls, hand, trump, table, gamedata):
        """Legacy protocol clients may omit metadata; keep their old fallback."""
        if not {'deck_count', 'enemy_count', 'discarded'} <= gamedata.keys():
            return False
        deck, enemy = gamedata['deck_count'], gamedata['enemy_count']
        if not isinstance(deck, int) or not isinstance(enemy, int) or deck < 0 or enemy < 0:
            return False
        table = tuple(map(DurakCard, table))
        discarded = tuple(map(DurakCard, gamedata['discarded']))
        visible = hand | set(table) | set(discarded)
        return (len(visible) == len(hand) + len(table) + len(discarded)
                and len(visible) + deck + enemy == 36 and (not deck or trump not in visible))

    def probability_has(self, cards):
        """Hypergeometric probability, conditional on certain pickup cards."""
        cards = set(cards)
        if cards & self.known_enemy:
            return 1.0
        hits = len(cards & self.unknown)
        total, count = len(self.unknown), self.unknown_count
        return 1.0 - comb(total - hits, count) / comb(total, count)

    def move(self):
        return self._evaluator.choose('move')

    def respond(self):
        return self._evaluator.choose('respond')

    def give_more(self):
        return self._evaluator.choose('give_more')

    def explain(self, phase, chosen):
        return {**self._evaluator.explain(phase, chosen),
                'throw_limit': max(0, self.enemy_count - 1) if phase == 'give_more' else None,
                'belief': {'model': 'uniform unknown cards, conditioned on public cards and certain pickups',
                           'known_enemy': list(map(str, sorted(self.known_enemy))),
                           'possible_enemy': list(map(str, sorted(self.possible_enemy))),
                           'unknown_enemy_count': self.unknown_count,
                           'card_probabilities': {str(c): self.probability_has({c}) for c in sorted(DurakCard.all())},
                           'suit_probabilities': {s: self.probability_has({c for c in self.possible_enemy if c.suit == s})
                                                  for s in DurakCard.SUITS},
                           'rank_probabilities': {r: self.probability_has({c for c in self.possible_enemy if c.rank == r})
                                                  for r in DurakCard.RANKS}}}
