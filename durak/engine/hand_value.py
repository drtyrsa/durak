"""Analytic hand assessment: card resources and fractional defensive matching.

No deals are sampled and no games are rolled out. Fractional card weights are
public-belief marginals. Matching is a relaxation, not a win probability.
"""
from durak.utils.cards import DurakCard

CARDS = tuple(sorted(DurakCard.all()))
INDEX = {card: i for i, card in enumerate(CARDS)}


class HandAssessment:
    def __init__(self, trump, live):
        self.trump = trump
        self.suits = {s: [i for i, c in enumerate(CARDS) if c.suit == s]
                      for s in DurakCard.SUITS}
        self.resources = tuple(
            # A top trump controls exchanges in a way a low trump cannot.
            # That premium rises when higher trumps leave the live cards.
            (2.6 + .22 * c.numeric_rank + .8 / (1 + sum(
                other.suit == trump.suit and other > c for other in live))
             if c.suit == trump.suit else
             .12 * c.numeric_rank + .10 * sum(
                 other.suit == c.suit and other < c for other in live))
            for c in CARDS)

    def coverage(self, defenders, attacks):
        return self.defensive_shape(defenders, attacks)[0]

    def defensive_shape(self, defenders, attacks):
        """Maximum fractional matching for Durak's nested beating relations.

        Spend plain-suit capacity first, then cover trump attacks with trumps.
        Remaining trump capacity can cover any remaining plain attack. A card
        has at most its marginal weight of capacity, however many it can beat.
        """
        remaining = list(attacks)
        covered = spare_trumps = breadth = 0.0
        for suit, indices in self.suits.items():
            if suit == self.trump.suit:
                continue
            suit_covered = 0.0
            for rank, i in enumerate(indices):
                capacity = defenders[i]
                for j in indices[:rank]:
                    used = min(capacity, remaining[j])
                    covered += used
                    suit_covered += used
                    capacity -= used
                    remaining[j] -= used
                    if capacity <= 0:
                        break
            # Extra insurance for defending in several suits without a trump.
            # Multiple stoppers in one suit cannot earn this bonus repeatedly.
            breadth += min(1.0, suit_covered)
        indices = self.suits[self.trump.suit]
        for rank, i in enumerate(indices):
            capacity = defenders[i]
            for j in indices[:rank]:
                used = min(capacity, remaining[j])
                covered += used
                capacity -= used
                remaining[j] -= used
                if capacity <= 0:
                    break
            spare_trumps += capacity
        plain = sum(remaining[i] for s, ids in self.suits.items()
                    if s != self.trump.suit for i in ids)
        return covered + min(spare_trumps, plain), breadth

    def evaluate(self, ours, enemy, deck_count, initiative):
        own_count, enemy_count = sum(ours), sum(enemy)
        if deck_count == 0 and (own_count < .001 or enemy_count < .001):
            terminal = 0 if own_count < .001 and enemy_count < .001 else (
                100 if own_count < .001 else -100)
            return {'resources': 0.0, 'burden': 0.0, 'coverage': 0.0,
                    'suit_cover': 0.0, 'initiative': 0.0, 'terminal': terminal, 'score': terminal}
        burden = 1.0 + 1.4 * (1 - min(deck_count, 24) / 24)
        material = sum((a - b) * value for a, b, value in zip(ours, enemy, self.resources))
        own_cover, own_breadth = self.defensive_shape(ours, enemy)
        enemy_cover, enemy_breadth = self.defensive_shape(enemy, ours)
        cover = .65 * (own_cover - enemy_cover)
        breadth = .30 * (own_breadth - enemy_breadth)
        tempo = (.45 + .45 * (1 - min(deck_count, 24) / 24)) * initiative
        return {'resources': material, 'burden': burden * (enemy_count - own_count),
                'coverage': cover, 'suit_cover': breadth, 'initiative': tempo, 'terminal': None,
                'score': material + burden * (enemy_count - own_count) + cover + breadth + tempo}


def weights(cards):
    result = [0.0] * len(CARDS)
    for card in cards:
        result[INDEX[card]] = 1.0
    return result
