"""Smart Runner: determinized Monte Carlo middlegame plus the exact endgame.

While cards remain in the deck the opponent's hand and the deck order are
hidden. Smart Runner tracks exactly what is public, samples complete worlds
consistent with it, plays every candidate action to the end of the game in
each world with a fast simulator, and picks the best average result. Every
candidate is evaluated on the same worlds, so the comparison measures the
actions rather than luck. With an empty deck the game has perfect
information and the exact EndgameSolver decides.
"""
import argparse
from random import Random
from time import perf_counter
from zlib import crc32

from durak.engine.dummy import DummyEngine
from durak.engine.endgame import EndgameSolver, SearchLimitReached
from durak.engine.simulator import DRAW, GIVE, MOVE, RESPOND, STOPPED, Universe, rollout
from durak.utils.cards import DurakCard

ALL_CARDS = frozenset(DurakCard.all())


class SmartRunnerEngine(DummyEngine):
    """Monte Carlo over sampled hidden-card worlds; exact play with an empty deck.

    Middlegame settings (defaults are the measured best trade-off):

    - ``worlds``: maximum sampled worlds per decision. With ``race``, worlds
      come in batches of ``batch``; after ``min_worlds``, a candidate is dropped
      once it trails the leader on the shared worlds by ``z`` standard errors.
    - ``leaf_deck``: with at most this many cards in the deck, rollouts stop
      when the sampled deck runs out and the exact solver scores the
      position (``leaf_worlds`` worlds, ``leaf_nodes`` per leaf, ``leaf_budget``
      per decision). 0 disables exact leaves.
    """

    def __init__(self, worlds=2048, max_cards=12, max_nodes=500_000, swindle_depth=3,
                 seed=0, explain_decisions=False, leaf_deck=4, leaf_worlds=128,
                 leaf_nodes=5_000, leaf_budget=150_000,
                 race=True, min_worlds=128, batch=64, z=3.0):
        if worlds < 1 or min_worlds < 2 or batch < 1 or leaf_worlds < 1:
            raise ValueError('worlds, leaf_worlds and batch must be positive; min_worlds >= 2')
        if not 2 <= max_cards <= 36:
            raise ValueError('max_cards must be between 2 and 36')
        if max_nodes is not None and max_nodes < 1:
            raise ValueError('max_nodes must be positive or None')
        self.worlds = worlds
        self.max_cards = max_cards
        self.max_nodes = max_nodes
        self.swindle_depth = swindle_depth
        self.seed = seed
        self.explain_decisions = explain_decisions
        self.last_decision = None
        self.leaf_deck = leaf_deck
        self.leaf_worlds = leaf_worlds
        self.leaf_nodes = leaf_nodes
        self.leaf_budget = leaf_budget
        self.race = race
        self.min_worlds = min_worlds
        self.batch = batch
        self.z = z

    # Protocol --------------------------------------------------------------

    def init(self, trump):
        result = super().init(trump)
        self._trump_card = DurakCard(trump)
        self._universe = Universe(trump)
        self._enemy = set()  # cards the opponent is known to hold
        self._seen = set()  # last observed table plus our later plays
        self._solver = None
        self.last_decision = None
        return result

    def deal(self, cards, gamedata):
        result = super().deal(cards, gamedata)
        self._enemy.difference_update(self._cards)
        self._observe((), gamedata)
        return result

    def move(self, on_table, gamedata):
        return self._decide('move', on_table, gamedata)

    def respond(self, on_table, gamedata):
        return self._decide('respond', on_table, gamedata)

    def give_more(self, on_table, gamedata):
        return self._decide('give_more', on_table, gamedata)

    # Knowledge -------------------------------------------------------------

    def _observe(self, table, gamedata):
        """Update known opponent cards from what left the table and how.

        A card we saw on the table that is now neither on it, discarded, nor
        in our hand was picked up by the opponent (this includes our own
        throw-ins). Cards the opponent plays become public again. Taking may
        be voluntary, so it tells us nothing certain about their other cards.
        """
        if 'discarded' not in gamedata:
            return
        table = set(map(DurakCard, table))
        discarded = set(map(DurakCard, gamedata['discarded']))
        public = table | discarded
        self._enemy |= self._seen - public - self._cards
        self._enemy -= public | self._cards
        enemy_count = gamedata.get('enemy_count', len(self._enemy))
        if len(self._enemy) > enemy_count:
            self._enemy = set()  # inconsistent: forget, don't guess
        self._seen = table

    def _hidden(self, table, gamedata):
        """Return (unknown cards, opponent slots to fill), or None if inconsistent."""
        try:
            deck_count, enemy_count = gamedata['deck_count'], gamedata['enemy_count']
            discarded = set(map(DurakCard, gamedata['discarded']))
        except KeyError:
            return None
        unknown = ALL_CARDS - self._cards - set(table) - discarded - self._enemy
        slots = enemy_count - len(self._enemy)
        if slots < 0 or len(unknown) != slots + deck_count:
            return None
        if deck_count and self._trump_card not in unknown:
            return None  # the face-up trump is always the last card of the deck
        return unknown, slots, deck_count

    # Decisions -------------------------------------------------------------

    def _decide(self, phase, on_table, gamedata):
        started = perf_counter()
        table = list(map(DurakCard, on_table))
        self._observe(table, gamedata)
        hand_before = sorted(self._cards)
        info = {}
        cards = None
        hidden = self._hidden(table, gamedata)
        if hidden is not None and hidden[2] == 0:
            cards = self._exact(phase, table, hidden[0] | self._enemy, info)
        if cards is None and hidden is not None:
            cards = self._monte_carlo(phase, table, gamedata, hidden, info)
        if cards is None:
            info['strategy'] = 'dummy'
            output = str(getattr(super(), phase)(on_table, gamedata))
            cards = list(map(DurakCard, output.split()))
        else:
            self._cards.difference_update(cards)
        self._seen.update(cards)
        if self.explain_decisions:
            self.last_decision = dict(info, phase=phase, hand=list(map(str, hand_before)),
                                      on_table=list(map(str, table)), gamedata=gamedata,
                                      known_enemy=list(map(str, sorted(self._enemy))),
                                      chosen=list(map(str, cards)),
                                      elapsed_ms=(perf_counter() - started) * 1000)
        return ' '.join(map(str, cards))

    def _exact(self, phase, table, enemy, info):
        active = self._cards | enemy | set(table)
        if len(active) > self.max_cards:
            return None
        if self._solver is None or not active.issubset(self._solver.bits):
            self._solver = EndgameSolver(active, self._trump_card, self.max_nodes,
                                         self.swindle_depth)
        attacker, defender = (enemy, self._cards) if phase == 'respond' else (self._cards, enemy)
        try:
            solution = self._solver.solve(attacker, defender, table, phase)
        except SearchLimitReached:
            return None
        info.update(strategy='exact', outcome=solution.outcome, nodes=solution.nodes,
                    expected_vs_random=solution.expected_vs_random)
        return list(solution.cards)

    def _race(self, active, results):
        """Drop candidates clearly worse than the leader on the same worlds."""
        n = len(results[active[0]])
        leader = max(active, key=lambda i: (sum(results[i]), -i))
        keep = []
        for index in active:
            if index != leader:
                diffs = [a - b for a, b in zip(results[leader], results[index])]
                mean = sum(diffs) / n
                var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
                if mean > 0 and mean * mean * n > self.z * self.z * var:
                    continue
            keep.append(index)
        return keep

    def _leaf(self, solver, hands, attacker):
        """Exact result of a sampled world once its deck is empty."""
        u = self._universe
        try:
            outcome = solver.solve(u.unpack(hands[attacker]), u.unpack(hands[1 - attacker])).outcome
        except SearchLimitReached:  # too big to solve quickly: finish the rollout
            return rollout(u, hands, [], attacker, 0, 0, MOVE)
        return DRAW if outcome == 0 else attacker if outcome == 1 else 1 - attacker

    def _candidates(self, phase, mine, table, pending, enemy_count):
        """Legal actions as simulator masks, cheapest first; 0 = stop/take/none."""
        u = self._universe
        if phase == 'respond':
            return self._bits(mine & u.beaters[pending.bit_length() - 1]) + [0]
        if phase == 'move':
            if not table:
                return self._bits(mine)
            return self._bits(mine & u.ranks(table)) + [0]
        # Throw-ins: the cheapest k eligible cards for every legal k. This is
        # a deliberate restriction (subsets grow exponentially); the exact
        # endgame still considers every subset once the deck is empty.
        eligible = self._bits(mine & u.ranks(table))[:max(0, enemy_count - 1)]
        prefixes, given = [0], 0
        for bit in eligible:
            given |= bit
            prefixes.append(given)
        return prefixes

    @staticmethod
    def _bits(mask):
        bits = []
        while mask:
            low = mask & -mask
            mask ^= low
            bits.append(low)
        return bits

    def _monte_carlo(self, phase, table, gamedata, hidden, info):
        u = self._universe
        unknown, slots, deck_count = hidden
        mine, table_mask = u.mask(self._cards), u.mask(table)
        pending = u.bit[table[-1]] if phase == 'respond' else 0
        candidates = self._candidates(phase, mine, table_mask, pending, gamedata['enemy_count'])
        if len(candidates) == 1:
            info['strategy'] = 'forced'
            return u.unpack(candidates[0])
        known = u.mask(self._enemy)
        bottom = u.bit[self._trump_card] if deck_count else 0
        pool = sorted(u.bit[card] for card in unknown if u.bit[card] != bottom)
        key = '|'.join(map(str, (self.seed, phase, sorted(self._cards), table,
                                 sorted(unknown), sorted(self._enemy))))
        rng = Random(crc32(key.encode()))
        attacker = 1 if phase == 'respond' else 0
        mode = {'move': MOVE, 'respond': RESPOND, 'give_more': GIVE}[phase]
        worlds = self.worlds if deck_count else 1  # an empty deck hides nothing
        exact_leaves = 0 < deck_count <= self.leaf_deck
        if exact_leaves:
            worlds = min(worlds, self.leaf_worlds)
        results = [[] for _ in candidates]  # per-world outcome, shared worlds
        active = list(range(len(candidates)))
        budget, exact_worlds = self.leaf_budget, 0
        done = 0
        batch = self.batch if self.race else worlds
        while done < worlds and len(active) > 1:
            for _ in range(min(batch, worlds - done)):
                done += 1
                rng.shuffle(pool)
                hand = pool[:slots]
                enemy = known | sum(hand)
                deck = ([bottom] if bottom else []) + pool[slots:]
                # Exact leaves per whole world, so all candidates are judged alike.
                solver = None
                if exact_leaves and budget > 0:
                    live = u.unpack(mine | enemy | table_mask | sum(deck))
                    solver = EndgameSolver(live, self._trump_card, self.leaf_nodes,
                                           swindle_depth=0)
                    exact_worlds += 1
                for index in active:
                    hands = [mine, enemy]
                    winner = rollout(u, hands, deck[:], attacker, table_mask, pending, mode,
                                     candidates[index], stop_at_empty=solver is not None)
                    if winner >= STOPPED:
                        winner = self._leaf(solver, hands, winner - STOPPED)
                        budget -= solver.nodes
                    results[index].append((winner == 0) - (winner == 1))
            if self.race and done >= self.min_worlds:
                active = self._race(active, results)
        mean = [sum(r) / len(r) if r else 0 for r in results]
        best = max(active, key=lambda i: (mean[i], -i))
        info.update(strategy='monte_carlo', worlds=done, exact_worlds=exact_worlds, candidates=[
            {'cards': list(map(str, u.unpack(c))), 'score': mean[i], 'worlds': len(results[i])}
            for i, c in enumerate(candidates)])
        return u.unpack(candidates[best])


def main():
    parser = argparse.ArgumentParser(description='Smart Runner Durak engine (stdin/stdout protocol)')
    parser.add_argument('--worlds', type=int, default=2048,
                        help='maximum sampled worlds per middlegame decision (default: 2048)')
    parser.add_argument('--no-race', action='store_true',
                        help='always evaluate every candidate on all worlds')
    parser.add_argument('--leaf-deck', type=int, default=4,
                        help='score rollouts exactly once the deck has at most this many '
                             'cards (default: 4; 0: off)')
    parser.add_argument('--max-cards', type=int, default=12,
                        help='maximum live cards for the exact endgame (default: 12)')
    parser.add_argument('--max-nodes', type=int, default=500_000,
                        help='exact endgame positions per decision (default: 500000; 0: unlimited)')
    args = parser.parse_args()
    try:
        engine = SmartRunnerEngine(args.worlds, args.max_cards, args.max_nodes or None,
                                   leaf_deck=args.leaf_deck, race=not args.no_race)
    except ValueError as error:
        parser.error(str(error))
    engine.run()


if __name__ == '__main__':
    main()
