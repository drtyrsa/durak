"""Exact, on-demand endgame tables for the rules in GameController.

Values are win/draw/loss, assuming optimal opposition. A successful defence
reduces the live card count. A pickup keeps the attacker, with fewer cards.
Consequently the game graph is acyclic: no repetition heuristic is needed.
"""
from dataclasses import dataclass
from itertools import combinations

from durak.utils.cards import DurakCard


class SearchLimitReached(Exception):
    """The search budget expired; an exact root result is not available."""


@dataclass(frozen=True)
class Solution:
    outcome: int  # +1 win, 0 draw, -1 loss, for the player choosing the action
    cards: tuple  # empty means stop attacking / pick up / throw nothing
    nodes: int  # previously uncached positions evaluated by this call


class EndgameSolver:
    """A reusable table for one set of live cards and its descendants.

    Cards use compact bit masks; the table's order and completed pairings do
    not matter. Only the uncovered attack must be recorded separately.
    ``max_nodes=None`` allows an unlimited exact search. With a budget, only
    fully solved positions are cached, including when a search is interrupted.
    """

    def __init__(self, cards, trump, max_nodes=None):
        self.trump = DurakCard(trump)
        self.cards = tuple(sorted(set(map(DurakCard, cards)), key=lambda c: (
            c.suit == self.trump.suit, c.numeric_rank, c.suit
        )))
        self.bits = {card: 1 << i for i, card in enumerate(self.cards)}
        self.beaters = {}
        self.same_rank = {}
        for card, bit in self.bits.items():
            self.beaters[bit] = sum(
                other_bit for other, other_bit in self.bits.items()
                if (other.suit == card.suit and other.numeric_rank > card.numeric_rank)
                or (other.suit == self.trump.suit and card.suit != self.trump.suit)
            )
            self.same_rank[bit] = sum(
                other_bit for other, other_bit in self.bits.items()
                if other.numeric_rank == card.numeric_rank
            )
        if max_nodes is not None and max_nodes < 1:
            raise ValueError('max_nodes must be positive or None')
        self.max_nodes = max_nodes
        self.table = {}
        self.nodes = 0

    def _mask(self, cards):
        mask = 0
        for card in cards:
            bit = self.bits[DurakCard(card)]
            if mask & bit:
                raise ValueError('Duplicate card')
            mask |= bit
        return mask

    def solve(self, attacker, defender, on_table=(), phase='move'):
        """Return an optimal action for ``move``, ``respond`` or ``give_more``.

        Hands always belong to the bout's attacker and defender, respectively.
        Like the wire protocol, on_table contains alternating attacks/defences.
        """
        on_table = tuple(on_table)
        a, d, t = self._mask(attacker), self._mask(defender), self._mask(on_table)
        if a & d or a & t or d & t:
            raise ValueError('Hands and table must be disjoint')
        if phase not in ('move', 'respond', 'give_more'):
            raise ValueError('Unknown phase: ' + phase)
        if len(on_table) % 2 != (phase != 'move'):
            raise ValueError('Table does not match the phase')
        # 0: attacker chooses; -1: attacker throws after a pickup;
        # positive bit: defender must beat this uncovered card or pick up.
        pending = (self.bits[DurakCard(on_table[-1])] if phase == 'respond'
                   else -1 if phase == 'give_more' else 0)
        self.nodes = 0
        value, action = self._search(a, d, t, pending)
        cards = tuple(card for card, bit in self.bits.items() if action & bit)
        return Solution(-value if phase == 'respond' else value, cards, self.nodes)

    def _eligible(self, hand, on_table):
        ranks = 0
        while on_table:
            bit = on_table & -on_table
            on_table ^= bit
            ranks |= self.same_rank[bit]
        return hand & ranks

    def _search(self, a, d, t, pending):
        key = (a, d, t, pending)
        cached = self.table.get(key)
        if cached is not None:
            return cached
        if self.max_nodes is not None and self.nodes >= self.max_nodes:
            raise SearchLimitReached
        self.nodes += 1

        # Match the controller's immediate finish and last-card draw rule.
        if not d:
            result = (-1 if a else 0, 0)
        elif not a and not (pending > 0 and d.bit_count() == 1
                            and self.beaters[pending] & d):
            result = (1, 0)
        else:
            target = -1 if pending > 0 else 1  # defender minimizes
            best, action = -2 * target, 0
            for candidate, child, sign in self._children(a, d, t, pending):
                value = sign * self._search(*child)[0]
                if target * value > target * best:
                    best, action = value, candidate
                if best == target:  # a proven win cannot be improved
                    break
            result = (best, action)

        # Bound memory as well as work per call. Entries are always exact.
        if self.max_nodes is None or len(self.table) < self.max_nodes:
            self.table[key] = result
        return result

    def _children(self, a, d, t, pending):
        if pending == 0:
            eligible = a if not t else self._eligible(a, t)
            while eligible:
                bit = eligible & -eligible
                eligible ^= bit
                yield bit, (a ^ bit, d, t | bit, bit), 1
            if t:
                # Successful defence: discard the table and exchange roles.
                yield 0, (d, a, 0, 0), -1
        elif pending > 0:
            eligible = d & self.beaters[pending]
            while eligible:
                bit = eligible & -eligible
                eligible ^= bit
                yield bit, (a, d ^ bit, t | bit, 0), 1
            # Taking voluntarily can be better than spending a winning card.
            yield 0, (a, d, t, -1), 1
        else:
            eligible = self._eligible(a, t)
            limit = d.bit_count() - 1
            # Every legal subset matters, including none and trump cards.
            # Generate only legal sizes: scanning all 2**k subsets is costly
            # when a large attacking hand can throw just one or two cards.
            bits = []
            while eligible:
                bit = eligible & -eligible
                eligible ^= bit
                bits.append(bit)
            for count in range(min(limit, len(bits)), -1, -1):
                for selected in combinations(bits, count):
                    subset = sum(selected)
                    yield subset, (a ^ subset, d | t | subset, 0, 0), 1
