"""Smart Runner: determinized Monte Carlo middlegame plus the exact endgame.

While cards remain in the deck the opponent's hand and the deck order are
hidden. Smart Runner tracks exactly what is public, samples complete worlds
consistent with it, plays every candidate action to the end of the game in
each world with a fast simulator, and compares the average results. Close,
uncertain scores favour preserving useful cards. Every candidate sees the
same worlds and continuation policies. With an empty deck the game has
perfect information and the exact EndgameSolver is tried within a node budget.
"""
import argparse
from math import sqrt
from random import Random
from time import perf_counter
from zlib import crc32

from durak.engine.dummy import DummyEngine
from durak.engine.endgame import EndgameSolver, SearchLimitReached
from durak.engine.simulator import DRAW, GIVE, MOVE, RESPOND, STOPPED, Universe, pickup, rollout
from durak.utils.cards import DurakCard

ALL_CARDS = frozenset(DurakCard.all())


class SmartRunnerEngine(DummyEngine):
    """Monte Carlo over sampled hidden-card worlds; exact play with an empty deck.

    All entry points use the same policy: mixed greedy/selective continuations,
    immediate pickup checks on costly attacks, and conservative close choices.
    Resource settings:

    - ``worlds``: maximum sampled worlds per decision. With ``race``, worlds
      come in batches of ``batch``; after ``min_worlds``, a candidate is dropped
      once it trails the leader on the shared worlds by ``z`` standard errors.
    - ``leaf_deck``: with at most this many cards in the deck, rollouts stop
      when the sampled deck runs out and the exact solver scores the
      position (``leaf_worlds`` worlds, ``leaf_nodes`` per leaf, ``leaf_budget``
      per decision). 0 disables exact leaves.
    - ``max_nodes``: exact search budget when the deck is empty. By default
      ``max_cards`` permits the entire deck, so even a large position gets a
      chance to be solved. Budget exhaustion falls back to a rollout.
    """

    def __init__(self, worlds=2048, max_cards=36, max_nodes=500_000, swindle_depth=3,
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
                                      settings={'policy_revision': 3, 'seed': self.seed,
                                                'worlds': self.worlds, 'race': self.race,
                                                'min_worlds': self.min_worlds, 'batch': self.batch,
                                                'z': self.z, 'max_cards': self.max_cards,
                                                'max_nodes': self.max_nodes,
                                                'swindle_depth': self.swindle_depth,
                                                'leaf_deck': self.leaf_deck,
                                                'leaf_worlds': self.leaf_worlds,
                                                'leaf_nodes': self.leaf_nodes,
                                                'leaf_budget': self.leaf_budget},
                                      elapsed_ms=(perf_counter() - started) * 1000)
        return ' '.join(map(str, cards))

    def _exact(self, phase, table, enemy, info):
        active = self._cards | enemy | set(table)
        if len(active) > self.max_cards:
            info['exact_search'] = {'status': 'card_limit', 'live_cards': len(active)}
            return None
        if self._solver is None or not active.issubset(self._solver.bits):
            self._solver = EndgameSolver(active, self._trump_card, self.max_nodes,
                                         self.swindle_depth)
        attacker, defender = (enemy, self._cards) if phase == 'respond' else (self._cards, enemy)
        try:
            solution = self._solver.solve(attacker, defender, table, phase)
        except SearchLimitReached:
            info['exact_search'] = {'status': 'node_limit', 'live_cards': len(active),
                                    'nodes': self._solver.nodes}
            return None
        info['exact_search'] = {'status': 'solved', 'live_cards': len(active)}
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

    def _leaf(self, solver, hands, attacker, careful=0):
        """Exact result of a sampled world once its deck is empty."""
        u = self._universe
        try:
            outcome = solver.solve(u.unpack(hands[attacker]), u.unpack(hands[1 - attacker])).outcome
        except SearchLimitReached:  # too big to solve quickly: finish the rollout
            return rollout(u, hands, [], attacker, 0, 0, MOVE, careful=careful)
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

    def _conservation_cost(self, phase, candidate, mine, table):
        """Prefer keeping useful cards only when rollout estimates are close."""
        u = self._universe
        if phase == 'respond' and not candidate:
            # A small pickup may buy a high card; several cards or an already
            # large hand cost tempo and make another pickup less attractive.
            useful = sum(bool(bit & u.trumps) or u.rank[bit.bit_length() - 1] >= 6
                         for bit in self._bits(table))
            return (0.8 + 0.4 * (table.bit_count() - 1)
                    + 0.15 * max(0, (mine | table).bit_count() - 6) - 0.2 * useful)
        cost = 0
        for bit in self._bits(candidate):
            rank = u.rank[bit.bit_length() - 1] / 8
            cost += (1.5 + rank if bit & u.trumps
                     else rank if phase == 'respond' else rank - 1)
        return cost

    def _pickup_replies(self, mine, enemy, deck, table, known):
        """Probe holding throw-ins as well as giving cheap cards, then a known lead.

        Only publicly remembered cards may be chosen as threats. Keep the two
        most costly to defend before refilling, bounding work even when
        much of the opponent's hand is known. No hidden-hand exclusions follow
        from the real opponent choosing a different continuation.
        """
        u = self._universe
        eligible = enemy & u.ranks(table) & u.plain
        given = sum(self._bits(eligible)[:max(0, mine.bit_count() - 1)])

        def difficulty(card):
            beaters = (mine | table) & u.beaters[card.bit_length() - 1]
            cheapest = beaters & -beaters
            return (3 if not cheapest else self._conservation_cost(
                'respond', cheapest, mine | table, card), -card)

        # Choose a fixed shortlist before draws, shared by every sampled world.
        threats = sorted(self._bits(known), key=difficulty, reverse=True)[:2]
        for scheme, thrown in (('hold', 0), ('cheap', given)):
            hands, remaining = [mine, enemy], deck[:]
            terminal = pickup(hands, remaining, 1, table, thrown)
            if terminal is not None:
                continue  # baseline rollout already covers a terminal pickup
            for threat in threats:
                if hands[1] & threat:
                    yield (scheme, threat), hands[:], remaining

    def _resistance(self, hands, attacker):
        """A secondary endgame measure, not a probability or an exact result.

        Fewer cards, unanswerable threats, trump strength, matching ranks and
        initiative offer practical chances when every sampled outcome loses.
        Both hands belong to this sampled world, not the actual hidden state.
        """
        u = self._universe
        if not all(hands):
            # Once a player is out, "unanswerable cards" have no tactical
            # value. In a lost finish, fewer cards left is the useful measure.
            return hands[1].bit_count() - hands[0].bit_count()

        def strength(own, enemy):
            threats = trumps = 0
            ranks = set()
            for bit in self._bits(own):
                index = bit.bit_length() - 1
                threats += not (enemy & u.beaters[index])
                if bit & u.trumps:
                    trumps += (u.rank[index] + 1) / 9
                ranks.add(u.rank[index])
            return (-own.bit_count() + 1.5 * threats + 0.5 * trumps
                    + 0.25 * (own.bit_count() - len(ranks)))

        return (strength(hands[0], hands[1]) - strength(hands[1], hands[0])
                + (0.5 if attacker == 0 else -0.5))

    @staticmethod
    def _worst_pickup_plan(continuations, plans):
        """One opponent plan across all worlds, including the usual policy."""
        return min([(None, continuations), *plans.items()], key=lambda p: (
            sum(r[0] for r in p[1]), sum(r[1] for r in p[1])))

    def _select(self, active, results, costs, resistance=None):
        """Break uncertain, small score differences toward conserving cards.

        Use paired samples, as in racing, and cap the allowed difference at
        0.03 (1.5 percentage points of game score). A clear tactical advantage
        always wins; low sample counts cannot grant an arbitrarily large tie.
        """
        means = [sum(r) / len(r) if r else 0 for r in results]
        leader = max(active, key=lambda i: (means[i], -i))
        if resistance is not None and means[leader] == -1:
            chosen = max(active, key=lambda i: (resistance[i], -costs[i], -i))
            return chosen, leader, means
        close = [leader]
        for i in active:
            if i == leader:
                continue
            diffs = [a - b for a, b in zip(results[leader], results[i])]
            n = len(diffs)
            gap = sum(diffs) / n
            se = sqrt(sum((d - gap) ** 2 for d in diffs) / (n * (n - 1))) if n > 1 else 0
            if gap <= min(0.03, se):
                close.append(i)
        chosen = min(close, key=lambda i: (costs[i], -means[i], i))
        return chosen, leader, means

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
        continuation_totals = [0] * len(candidates)
        resistance_totals = [0.0] * len(candidates)
        assess_resistance = deck_count <= 6
        active = list(range(len(candidates)))
        costs = [self._conservation_cost(phase, c, mine, table_mask) for c in candidates]
        budget, exact_worlds = self.leaf_budget, 0
        reply_checks = 0
        pickup_checks = pickup_threats = 0
        pickup_plans = {}
        take_continuations = []
        pickup_plan = None
        done = 0
        batch = self.batch if self.race else worlds
        while done < worlds and len(active) > 1:
            for _ in range(min(batch, worlds - done)):
                done += 1
                rng.shuffle(pool)
                hand = pool[:slots]
                enemy = known | sum(hand)
                deck = ([bottom] if bottom else []) + pool[slots:]
                # Shared continuation styles prevent every sampled player
                # from spending its last good trump just because it can beat.
                careful = 3 if done % 2 else 0
                # Exact leaves per whole world, so all candidates are judged alike.
                solver = None
                if exact_leaves and budget > 0:
                    live = u.unpack(mine | enemy | table_mask | sum(deck))
                    solver = EndgameSolver(live, self._trump_card, self.leaf_nodes,
                                           swindle_depth=0)
                    exact_worlds += 1
                def evaluate(hands, attack_seat, on_table, uncovered, stage, action,
                             draw_pile=None):
                    nonlocal budget
                    pile = deck if draw_pile is None else draw_pile
                    winner = rollout(u, hands, pile[:], attack_seat, on_table, uncovered, stage,
                                     action, stop_at_empty=solver is not None or assess_resistance,
                                     careful=careful)
                    next_attacker = winner - STOPPED if winner >= STOPPED else attack_seat
                    fight = self._resistance(hands, next_attacker) if assess_resistance else 0
                    if winner >= STOPPED:
                        if solver is not None:
                            winner = self._leaf(solver, hands, next_attacker, careful)
                            budget -= solver.nodes
                        else:
                            winner = rollout(u, hands, [], next_attacker, 0, 0, MOVE,
                                             careful=careful)
                    return (winner == 0) - (winner == 1), fight

                for index in active:
                    candidate = candidates[index]
                    result = evaluate([mine, enemy], attacker, table_mask, pending, mode, candidate)
                    continuation_totals[index] += result[0]
                    if mode == MOVE and candidate and deck and done % 4 == 0:
                        choices = enemy & u.beaters[candidate.bit_length() - 1]
                        cheapest = choices & -choices
                        if cheapest & u.trumps:
                            # In a quarter of worlds the opponent checks both
                            # a costly defence and a voluntary pickup instead
                            # of cooperating with our attempt to draw a trump.
                            reply_table = table_mask | candidate
                            # These worlds use the greedy continuation above;
                            # explicitly compare its defence with taking.
                            alternative = evaluate([mine ^ candidate, enemy], 0, reply_table,
                                                   candidate, RESPOND, 0)
                            result = min(result, alternative)
                            reply_checks += 1
                    if mode == RESPOND and not candidate and deck and known:
                        take_continuations.append(result)
                        for outcomes in pickup_plans.values():
                            outcomes.append(result)
                        if deck_count <= 6 or done % 4 == 0:
                            evaluated = {}
                            for plan, reply_hand, reply_deck in self._pickup_replies(
                                    mine, enemy, deck, table_mask, known):
                                threat = plan[1]
                                key = (*reply_hand, tuple(reply_deck), threat)
                                if key not in evaluated:
                                    evaluated[key] = evaluate(reply_hand, 1, 0, 0, MOVE,
                                                              threat, reply_deck)
                                    pickup_checks += 1
                                if plan not in pickup_plans:
                                    pickup_plans[plan] = take_continuations[:]
                                pickup_plans[plan][-1] = evaluated[key]
                                pickup_threats |= threat
                    score, fight = result
                    results[index].append(score)
                    resistance_totals[index] += fight
            if pickup_plans:
                # The opponent chooses one plan on average, not a different
                # best reply using foreknowledge of every sampled deck order.
                pickup_plan, worst = self._worst_pickup_plan(take_continuations, pickup_plans)
                take_index = candidates.index(0)
                results[take_index] = [r[0] for r in worst]
                resistance_totals[take_index] = sum(r[1] for r in worst)
            if self.race and done >= self.min_worlds:
                active = self._race(active, results)
        resistance = [total / len(r) if r else 0
                      for total, r in zip(resistance_totals, results)] if assess_resistance else None
        best, leader, mean = self._select(active, results, costs, resistance)
        selection = ('resistance' if assess_resistance and mean[leader] == -1
                     else 'conservation' if best != leader else 'score')
        info.update(strategy='monte_carlo', worlds=done, exact_worlds=exact_worlds,
                    reply_checks=reply_checks, pickup_checks=pickup_checks,
                    pickup_threats=list(map(str, u.unpack(pickup_threats))), selection=selection,
                    pickup_plan=({'throw_in': pickup_plan[0],
                                  'attack': str(u.unpack(pickup_plan[1])[0])}
                                 if pickup_plan is not None else None),
                    score_leader=list(map(str, u.unpack(candidates[leader]))), candidates=[
            {'cards': list(map(str, u.unpack(c))), 'score': mean[i], 'worlds': len(results[i]),
             'continuation_score': continuation_totals[i] / len(results[i]),
             'resistance': resistance[i] if resistance is not None else None,
             'conservation_cost': costs[i]}
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
    parser.add_argument('--max-cards', type=int, default=36,
                        help='maximum live cards for the exact endgame (default: 36; '
                             'search is limited by --max-nodes)')
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
