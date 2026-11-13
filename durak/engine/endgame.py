"""Exact, on-demand endgame tables for the rules in GameController.

Values are win/draw/loss, assuming optimal opposition. A successful defence
reduces the live card count. A pickup keeps the attacker, with fewer cards.
Consequently the game graph is acyclic: no repetition heuristic is needed.
"""
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from typing import Optional

from durak.utils.cards import DurakCard


class SearchLimitReached(Exception):
    """The search budget expired; an exact root result is not available."""


@dataclass(frozen=True)
class Solution:
    outcome: int  # +1 win, 0 draw, -1 loss, for the player choosing the action
    cards: tuple  # empty means stop attacking / pick up / throw nothing
    nodes: int  # previously uncached positions evaluated by this call
    # Only for drawn/lost positions: expected outcome of the chosen action if
    # the opponent picks uniformly at random (see EndgameSolver.swindle_depth).
    expected_vs_random: Optional[float] = None


class EndgameSolver:
    """A reusable table for one set of live cards and its descendants.

    Cards use compact bit masks; the table's order and completed pairings do
    not matter. Only the uncovered attack must be recorded separately.
    ``max_nodes=None`` allows an unlimited exact search. With a budget, only
    fully solved positions are cached, including when a search is interrupted,
    and the table holds at most ``max_nodes`` entries unless ``cache_size``
    supplies a separate memory limit for reuse across bounded searches.

    Exact play is indifferent between moves with the same value. When the
    player to act cannot force a win, ties are broken toward the move whose
    expected outcome is best if the opponent chooses uniformly at random for
    their next ``swindle_depth`` decisions, while our own choices stay exact.
    ``swindle_depth=0`` disables this and keeps the generation-order choice.
    """

    def __init__(self, cards, trump, max_nodes=None, swindle_depth=3, cache_size=None):
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
        if swindle_depth < 0:
            raise ValueError('swindle_depth must be non-negative')
        if cache_size is not None and cache_size < 1:
            raise ValueError('cache_size must be positive or None')
        self.max_nodes = max_nodes
        self.cache_size = cache_size
        self.swindle_depth = swindle_depth
        self.table = {}
        self.nodes = 0
        self._root_live = 0
        self._call_start = 0

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
        self._root_live = a | d | t
        self._call_start = len(self.table)  # dicts keep insertion order
        self.nodes = 0
        value, action = self._search(a, d, t, pending)
        persp = -1 if pending > 0 else 1  # converts attacker values to ours
        expected = None
        if (persp * value < 1 and self.swindle_depth
                and self._terminal(a, d, pending) is None):
            try:
                action, expected = self._swindle((a, d, t, pending), persp, persp * value)
            except SearchLimitReached:
                pass  # keep the exact default action
        cards = tuple(card for card, bit in self.bits.items() if action & bit)
        return Solution(persp * value, cards, self.nodes,
                        None if expected is None else float(expected))

    def cached_outcome(self, attacker, defender):
        """Known attacker-relative value at an empty table; no search or mutation.

        None means unknown, including searches previously stopped by a budget.
        A proven draw is 0. Terminal positions need no search either.
        """
        a, d = self._mask(attacker), self._mask(defender)
        if a & d:
            raise ValueError('Hands must be disjoint')
        cached = self.table.get((a, d, 0, 0))
        return cached[0] if cached is not None else self._terminal(a, d, 0)

    def _evict(self, capacity):
        """Make room in a full table by dropping entries from earlier calls.

        Refusing new entries instead would make the search re-expand shared
        subtrees and exhaust its budget on positions a fresh solver handles.
        Earlier entries using a card outside the root's live set are
        unreachable and go first; if that is not enough, all earlier entries
        go. With the default capacity, this leaves room for everything the
        current call can solve. An explicitly smaller cache also drops older
        entries from this call as necessary.
        """
        items = list(self.table.items())
        live = self._root_live
        old = [(key, value) for key, value in items[:self._call_start]
               if not (key[0] | key[1] | key[2]) & ~live]
        new = items[self._call_start:]
        if len(old) + len(new) >= capacity:
            old = []
        if len(new) >= capacity:
            # An explicitly small cache may fill within a single search.
            # Dropping completed entries only affects speed, never exactness.
            new = new[-(capacity // 2):] if capacity > 1 else []
        self.table = dict(old + new)
        self._call_start = len(old)

    def _terminal(self, a, d, pending):
        """Exact value of a finished game, or None while play continues."""
        # Match the controller's immediate finish and last-card draw rule.
        if not d:
            return -1 if a else 0
        if not a and not (pending > 0 and d.bit_count() == 1
                          and self.beaters[pending] & d):
            return 1
        return None

    def _swindle(self, state, persp, value):
        """Among actions keeping the exact ``value``, maximize expected_vs_random.

        Returns (action, expectation); the expectation is None when only one
        action keeps the exact value, so there is no tie to break.
        """
        optimal = [(candidate, child, persp * sign)
                   for candidate, child, sign in self._children(*state)
                   if persp * sign * self._search(*child)[0] == value]
        if len(optimal) == 1:
            return optimal[0][0], None
        memo = {}
        best, action = None, 0
        for candidate, child, child_persp in optimal:
            score = self._expect(child, child_persp, self.swindle_depth, memo)
            if best is None or score > best:  # ties keep generation order
                best, action = score, candidate
        return action, best

    def _expect(self, state, persp, depth, memo):
        """Our expected value: we play exactly, the opponent uniformly at random.

        ``depth`` counts the opponent decisions still modelled as random; after
        that, both sides are assumed to play perfectly. ``persp`` converts the
        state's attacker-relative values to ours.
        """
        key = (state, persp, depth)
        if key in memo:
            return memo[key]
        value = persp * self._search(*state)[0]
        a, d, t, pending = state
        if depth == 0 or self._terminal(a, d, pending) is not None:
            return Fraction(value)
        ours = (pending <= 0) == (persp == 1)
        scores = []
        for _, child, sign in self._children(*state):
            child_persp = persp * sign
            if ours:  # never trade exactness for chances
                if child_persp * self._search(*child)[0] == value:
                    scores.append(self._expect(child, child_persp, depth, memo))
            else:
                scores.append(self._expect(child, child_persp, depth - 1, memo))
        result = max(scores) if ours else sum(scores, Fraction(0)) / len(scores)
        memo[key] = result
        return result

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

        terminal = self._terminal(a, d, pending)
        if terminal is not None:
            result = (terminal, 0)
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
        capacity = self.max_nodes if self.cache_size is None else self.cache_size
        if capacity is not None and len(self.table) >= capacity:
            self._evict(capacity)
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
