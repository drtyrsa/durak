"""Chance-only card luck, independent of engine policy and random number generators.

All values are signed for player 1, in game-score units. Each refill contributes
actual hand value minus its exact expectation over the unordered hidden stock.
The coefficients are fixed hypotheses, not calibrated winning probabilities.
See docs/luck.md for the estimator, assumptions and limitations.
"""
from collections import Counter
from math import comb, fsum

from durak.utils.cards import DurakCard


MODEL = 'chance-v1'
WEIGHTS = {'trumps': 0.06, 'ranks': 0.03, 'answers': 0.02,
           'pairs': 0.008, 'suits': 0.015}


def _answers(hand, attack):
    # Cheap same-suit cover: 8H against 7H, for example. An ace against a six
    # is legal but isn't the convenient fit this feature is trying to measure.
    return any(card.suit == attack.suit and
               0 < card.numeric_rank - attack.numeric_rank <= 2 for card in hand)


def features(hand, opponent, trump):
    """Unweighted hand features; hands contain DurakCards, trump is a suit."""
    ranks = Counter(card.numeric_rank for card in hand)
    return {
        'trumps': sum(card.suit == trump for card in hand),
        'ranks': sum(card.numeric_rank for card in hand) / 8,
        'answers': sum(_answers(hand, card) for card in opponent),
        'pairs': sum(comb(count, 2) for count in ranks.values()),
        'suits': len({card.suit for card in hand
                      if card.suit != trump and card.numeric_rank > 0}),
    }


def advantage(first, second, trump):
    """Feature contributions to player 1's advantage (not a win probability)."""
    a, b = features(first, second, trump), features(second, first, trump)
    return {key: weight * (a[key] - b[key]) for key, weight in WEIGHTS.items()}


def expected_advantage(hand, opponent, pool, count, trump):
    """Exact expected advantage after *hand* draws a uniform count-card subset.

    Expressed from the drawing player's perspective. Hypergeometric inclusion
    probabilities handle pairs, suit coverage and cheap answers without sampling.
    The opponent's ability to cover the new cards changes too.
    """
    if not 0 <= count <= len(pool):
        raise ValueError('draw count outside pool')
    if not count:
        return advantage(hand, opponent, trump)
    n = len(pool)
    fraction = count / n
    subsets = comb(n, count)

    def present(matches):
        return 1 - comb(n - matches, count) / subsets

    ours, theirs = features(hand, opponent, trump), features(opponent, hand, trump)
    ours['trumps'] += fraction * sum(card.suit == trump for card in pool)
    ours['ranks'] += fraction * sum(card.numeric_rank for card in pool) / 8
    ranks = Counter(card.numeric_rank for card in hand)
    pool_ranks = Counter(card.numeric_rank for card in pool)
    for rank, matches in pool_ranks.items():
        ours['pairs'] += ranks[rank] * fraction * matches
        if n > 1:
            ours['pairs'] += comb(matches, 2) * count * (count - 1) / (n * (n - 1))
    for suit in DurakCard.SUITS:
        if suit != trump and not any(c.suit == suit and c.numeric_rank > 0 for c in hand):
            ours['suits'] += present(sum(c.suit == suit and c.numeric_rank > 0 for c in pool))
    for attack in opponent:
        if not _answers(hand, attack):
            ours['answers'] += present(sum(_answers((card,), attack) for card in pool))
    theirs['answers'] += fraction * sum(_answers(opponent, card) for card in pool)
    return {key: weight * (ours[key] - theirs[key]) for key, weight in WEIGHTS.items()}


class LuckTracker:
    def __init__(self, first, second, trump):
        self.trump = DurakCard(trump).suit
        # Given the face-up trump, initial hands have the same distribution.
        # Antisymmetry therefore gives an exact zero expected difference.
        self.opening = advantage(first, second, self.trump)
        self.refills = dict.fromkeys(WEIGHTS, 0.0)
        self.refill_count = 0
        self.cards_drawn = 0

    def observe_refill(self, seat, first, second, stock, count):
        """Called before a real stock draw, after any table pickup.

        stock[-1] is public, so it is never part of the random pool. Taking all
        remaining cards is deterministic conditional on the current position.
        No credit is awarded for pickups or decisions to play/keep a card.
        """
        if seat not in (0, 1) or count < 0:
            raise ValueError('invalid refill')
        count = min(count, len(stock))
        if not count:
            return
        self.refill_count += 1
        self.cards_drawn += count
        if count == len(stock):
            return
        hand, opponent = (first, second) if seat == 0 else (second, first)
        expected = expected_advantage(hand, opponent, stock[:-1], count, self.trump)
        actual = advantage(list(hand) + stock[:count], opponent, self.trump)
        sign = 1 if seat == 0 else -1
        for key in WEIGHTS:
            self.refills[key] += sign * (actual[key] - expected[key])

    def report(self):
        components = {key: self.opening[key] + self.refills[key] for key in WEIGHTS}
        return {'model': MODEL, 'perspective': 'player1',
                'total': fsum(components.values()),
                'opening': fsum(self.opening.values()),
                'refills': fsum(self.refills.values()),
                'components': components, 'opening_components': self.opening.copy(),
                'refill_components': self.refills.copy(),
                'refill_count': self.refill_count, 'cards_drawn': self.cards_drawn}
