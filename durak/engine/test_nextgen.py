"""Headless validation against the real controller, not a second bitmask model."""
from fractions import Fraction
from itertools import combinations, product
import json
from random import Random
import subprocess
import sys
import unittest
from unittest.mock import patch

from durak.controller import GameController, Table
from durak.engine.dummy import DummyEngine
from durak.engine.endgame import EndgameSolver, SearchLimitReached
from durak.engine.nextgen import NextGenEngine
from durak.utils.cards import CardSet, DurakCard


PHASES = {'moving': 'move', 'responding': 'respond', 'giving_more': 'give_more'}


def game(attacker, defender, trump='6S', table=(), phase='moving'):
    controller = GameController()
    controller._logger_enabled = False
    controller._trump = DurakCard(trump)
    controller._deck = []
    controller._player1.cards = CardSet(attacker, trump)
    controller._player2.cards = CardSet(defender, trump)
    controller._to_move = controller._player1
    controller._on_table = Table(map(DurakCard, table))
    controller._discarded = list(DurakCard.all() - controller._player1.cards
                                - controller._player2.cards - set(controller._on_table))
    controller._no_response = phase == 'giving_more'
    controller._state = phase
    return controller


def clone(controller):
    result = game(controller._player1.cards, controller._player2.cards,
                  controller._trump, controller.on_table, controller.state)
    if not controller.is_player1_to_move():
        result._to_move = result._player2
    return result


def legal_actions(controller):
    phase = PHASES[controller.state]
    attacker, defender = controller._to_move.cards, controller._to_respond.cards
    if phase == 'move':
        actions = [(card,) for card in attacker.cards_that_can_be_added_to(controller.on_table)]
        return actions + ([()] if controller.on_table else [])
    if phase == 'respond':
        return [(card,) for card in defender.cards_that_can_beat(controller.on_table[-1])] + [()]
    eligible = attacker.cards_that_can_be_added_to(controller.on_table)
    return [cards for n in range(min(len(eligible), len(defender) - 1) + 1)
            for cards in combinations(eligible, n)]


def apply(controller, action):
    phase = PHASES[controller.state]
    getattr(controller, 'register_' + ('response' if phase == 'respond' else phase))(
        action if phase == 'give_more' else (action[0] if action else None))
    if controller.state == controller.States.DEALING:
        controller.deal()


class ControllerOracle:
    """Full-width minimax using only GameController for transitions/rules."""

    def __init__(self, test, solver):
        self.test = test
        self.solver = solver
        self.cache = {}
        self.phases = set()

    def solve(self, controller):
        if controller.is_game_over():
            return {controller.PLAYER1: 1, controller.PLAYER2: -1, None: 0}[controller.winner]
        key = (frozenset(controller._player1.cards), frozenset(controller._player2.cards),
               controller.is_player1_to_move(), tuple(controller.on_table), controller.state)
        if key in self.cache:
            return self.cache[key]
        phase = PHASES[controller.state]
        self.phases.add(phase)
        p1_acts = controller.is_player1_to_move() != (phase == 'respond')
        target = 1 if p1_acts else -1
        results = []
        for action in legal_actions(controller):
            child = clone(controller)
            apply(child, action)
            results.append((self.solve(child), frozenset(action)))
        best = max(value * target for value, _ in results) * target
        optimal = {action for value, action in results if value == best}
        solution = self.solver.solve(controller._to_move.cards, controller._to_respond.cards,
                                     controller.on_table, phase)
        self.test.assertEqual(solution.outcome, best * target, key)
        self.test.assertIn(frozenset(solution.cards), optimal, key)
        self.cache[key] = best
        return best


class SolverTest(unittest.TestCase):
    def test_every_one_against_one_for_every_trump_suit(self):
        deck = DurakCard.all()
        for suit in DurakCard.SUITS:
            trump = '6' + suit
            for attacker in deck:
                for defender in deck - {attacker}:
                    solver = EndgameSolver((attacker, defender), trump)
                    can_beat = bool(CardSet([defender], trump).cards_that_can_beat(attacker))
                    result = solver.solve([attacker], [defender])
                    self.assertEqual(result.outcome, 0 if can_beat else 1)
                    self.assertEqual(result.cards, (attacker,))

    def test_all_reachable_positions_in_six_card_universe_against_controller(self):
        cards = ('6C', '7C', '6D', '8D', '7S', '8S')
        oracle = ControllerOracle(self, EndgameSolver(cards, '6S'))
        # Every assignment to attacker / defender / discard, and every legal
        # continuation, including voluntary takes and all throw-in subsets.
        for assignment in product(range(3), repeat=len(cards)):
            attacker = [c for c, owner in zip(cards, assignment) if owner == 0]
            defender = [c for c, owner in zip(cards, assignment) if owner == 1]
            if attacker and defender:
                oracle.solve(game(attacker, defender))
        self.assertEqual(oracle.phases, {'move', 'respond', 'give_more'})
        self.assertGreater(len(oracle.cache), 1000)

    def test_last_card_beatable_by_one_card_draws(self):
        solver = EndgameSolver(['6C', '7C'], '6S')
        result = solver.solve([], ['7C'], ['6C'], 'respond')
        self.assertEqual(result.outcome, 0)
        self.assertEqual(tuple(map(str, result.cards)), ('7C',))

    def test_last_attack_wins_immediately_against_multiple_cards(self):
        solver = EndgameSolver(['6C', '7C', '8C'], '6S')
        self.assertEqual(solver.solve(['6C'], ['7C', '8C']).outcome, 1)

    def test_terminal_positions_return_no_action_or_tie_break_expectation(self):
        cases = [
            (['6C', '7C'], [], [], 'move', -1),
            (['6D'], [], ['6C', '7C'], 'move', -1),
            ([], ['7C', '8C'], ['6C'], 'respond', -1),
            ([], ['7C'], ['6D'], 'respond', -1),
            ([], ['7C'], [], 'move', 1),
            ([], [], ['6C', '7C'], 'move', 0),
        ]
        for attacker, defender, table, phase, outcome in cases:
            with self.subTest(attacker=attacker, defender=defender, table=table, phase=phase):
                solver = EndgameSolver(attacker + defender + table, '6S')
                for _ in range(2):  # also exercise a cached terminal root
                    result = solver.solve(attacker, defender, table, phase)
                    self.assertEqual(result.outcome, outcome)
                    self.assertEqual(result.cards, ())
                    self.assertIsNone(result.expected_vs_random)

    def test_strategy_regressions(self):
        # Greedy low cards, always defending, always throwing, and saving
        # trumps are all sometimes inferior to these proven winning choices.
        cases = [
            (['6C', '8D'], ['6D', '7C'], [], 'move', ('8D',)),
            (['7C'], ['7S', '8S', '6D', '6C'], ['8D'], 'respond', ('8S',)),
            (['7S', '6D', '6C'], ['8D', '8S'], ['7C'], 'give_more', ('7S',)),
            (['JC', 'QH', '7D'], ['AD', 'JS', 'TH', '9D'], ['7S'], 'respond', ()),
            (['7S', 'AD', 'QD'], ['6H', '6D', 'KH'], ['7H', 'TH'], 'move', ()),
        ]
        for attacker, defender, table, phase, expected in cases:
            with self.subTest(phase=phase, expected=expected):
                solver = EndgameSolver(attacker + defender + table, '6S')
                result = solver.solve(attacker, defender, table, phase)
                self.assertEqual(result.outcome, 1)
                self.assertEqual(tuple(map(str, result.cards)), expected)

    def test_six_against_six_and_reusing_table(self):
        cards = Random(42).sample(sorted(DurakCard.all()), 12)
        solver = EndgameSolver(cards, '6S', max_nodes=500_000)
        first = solver.solve(cards[:6], cards[6:])
        self.assertIn(first.cards[0], cards[:6])
        self.assertGreater(first.nodes, 0)
        second = solver.solve(cards[:6], cards[6:])
        self.assertEqual((first.outcome, first.cards), (second.outcome, second.cards))
        self.assertEqual(second.nodes, 0)

    def test_budget_never_caches_an_incomplete_result(self):
        solver = EndgameSolver(['6C', '7C', '8C', '9C'], '6S', max_nodes=1)
        with self.assertRaises(SearchLimitReached):
            solver.solve(['6C', '8C'], ['7C', '9C'])
        self.assertFalse(solver.table)
        solver.max_nodes = None
        result = solver.solve(['6C', '8C'], ['7C', '9C'])
        self.assertIn(result.outcome, (-1, 0, 1))

    def test_cached_outcomes_require_a_proof_and_include_draws(self):
        solver = EndgameSolver(['6C', '7C', '8C', '9C'], '6S', max_nodes=1,
                               swindle_depth=0, cache_size=100)
        hands = (['6C', '8C'], ['7C', '9C'])
        with self.assertRaises(SearchLimitReached):
            solver.solve(*hands)
        self.assertIsNone(solver.cached_outcome(*hands))
        solver.max_nodes = 100
        expected = solver.solve(*hands).outcome
        solver.max_nodes = 1
        nodes = solver.nodes
        self.assertEqual(solver.cached_outcome(*hands), expected)
        self.assertEqual(solver.nodes, nodes)
        solver.max_nodes = 100
        self.assertEqual(solver.solve(['6C'], ['7C']).outcome, 0)
        self.assertEqual(solver.cached_outcome(['6C'], ['7C']), 0)
        self.assertEqual(solver.cached_outcome([], []), 0)
        self.assertEqual(solver.cached_outcome([], ['7C']), 1)
        self.assertEqual(solver.cached_outcome(['6C'], []), -1)

    def test_cache_capacity_is_independent_of_search_budget(self):
        cards = ['6C', '7C', '8C', '9C', 'TD', 'JS']
        expected = EndgameSolver(cards, '6S', swindle_depth=0).solve(cards[:3], cards[3:])
        for capacity in (1, 5, 1000):
            solver = EndgameSolver(cards, '6S', max_nodes=1000, swindle_depth=0,
                                   cache_size=capacity)
            result = solver.solve(cards[:3], cards[3:])
            self.assertEqual(result.outcome, expected.outcome)
            self.assertLessEqual(len(solver.table), capacity)
            solver.max_nodes = 1
            self.assertEqual(solver.solve(cards[:3], cards[3:]).outcome, expected.outcome)
            self.assertEqual(solver.nodes, 0)

    def test_full_table_never_does_worse_than_a_fresh_solver(self):
        # A full table used to stop caching, so a long-lived solver ran out
        # of budget on positions that a fresh solver solved.
        rng = Random(5)
        cards = rng.sample(sorted(DurakCard.all()), 12)
        shared = EndgameSolver(cards, '6S', max_nodes=2000, swindle_depth=0)
        evictions = []
        evict = EndgameSolver._evict
        with patch.object(EndgameSolver, '_evict',
                          lambda solver, capacity: (evictions.append(1), evict(solver, capacity))):
            for _ in range(40):
                sub = rng.sample(cards, 10)
                try:
                    expected = EndgameSolver(sub, '6S', max_nodes=2000, swindle_depth=0).solve(
                        sub[:5], sub[5:])
                except SearchLimitReached:
                    continue
                self.assertEqual(shared.solve(sub[:5], sub[5:]).outcome, expected.outcome)
                self.assertLessEqual(len(shared.table), 2000)
        self.assertTrue(evictions)

    def test_eviction_keeps_reachable_entries_and_drops_unreachable_ones(self):
        solver = EndgameSolver(['6C', '7C', '8C', '9C', '6D', '7D'], '6S', max_nodes=10_000)
        solver.solve(['6C', '8C'], ['7C', '9C'])
        reachable = dict(solver.table)
        solver.solve(['6D'], ['7D'])
        solver._root_live = solver._mask(['6C', '7C', '8C', '9C'])
        solver._call_start = len(solver.table)
        solver._evict(capacity=10_000)
        self.assertEqual(solver.table, reachable)

    def test_tie_break_keeps_exact_value_and_seeks_chances(self):
        attacker, defender = ['QC', '9H', 'JC'], ['9S', 'QS', '7D']
        plain = EndgameSolver(attacker + defender, '6S', swindle_depth=0).solve(attacker, defender)
        swindle = EndgameSolver(attacker + defender, '6S').solve(attacker, defender)
        self.assertEqual((plain.outcome, swindle.outcome), (-1, -1))
        self.assertIsNone(plain.expected_vs_random)
        self.assertEqual(tuple(map(str, plain.cards)), ('9H',))  # hopeless vs. random replies
        self.assertEqual(tuple(map(str, swindle.cards)), ('JC',))
        self.assertGreater(swindle.expected_vs_random, 0.9)

    def test_tie_break_is_not_used_when_winning(self):
        solver = EndgameSolver(['6C', '8D', '6D', '7C'], '6S')
        result = solver.solve(['6C', '8D'], ['6D', '7C'])
        self.assertEqual(result.outcome, 1)
        self.assertIsNone(result.expected_vs_random)

    def test_expected_vs_random_matches_controller(self):
        # Independent expectimax over GameController transitions: we keep the
        # exact value, the opponent picks uniformly for `depth` decisions.
        rng = Random(11)
        deck = sorted(DurakCard.all())
        checked = set()
        for index in range(90):
            cards = rng.sample(deck, 6)
            trump = rng.choice(deck)
            oracle = ControllerOracle(self, EndgameSolver(cards, trump, swindle_depth=0))
            owners = [0, 1] + [rng.randrange(2) for _ in cards[2:]]
            controller = game([c for c, o in zip(cards, owners) if o == 0],
                              [c for c, o in zip(cards, owners) if o == 1], trump)
            target = ('moving', 'responding', 'giving_more')[index % 3]
            for _ in range(6):  # also reach respond / give_more roots
                if controller.is_game_over() or controller.state == target:
                    break
                apply(controller, rng.choice(legal_actions(controller)))
            if controller.is_game_over():
                continue
            phase = PHASES[controller.state]
            us = controller.is_player1_to_move() != (phase == 'respond')
            depth = rng.randrange(1, 4)

            def expect(node, depth):
                value = oracle.solve(node) * (1 if us else -1)
                if depth == 0 or node.is_game_over():
                    return Fraction(value)
                acting = node.is_player1_to_move() != (PHASES[node.state] == 'respond')
                scores = []
                for action in legal_actions(node):
                    child = clone(node)
                    apply(child, action)
                    if acting != us:
                        scores.append(expect(child, depth - 1))
                    elif oracle.solve(child) * (1 if us else -1) == value:
                        scores.append(expect(child, depth))
                return max(scores) if acting == us else sum(scores, Fraction(0)) / len(scores)

            value = oracle.solve(controller) * (1 if us else -1)
            options = {}
            for action in legal_actions(controller):
                child = clone(controller)
                apply(child, action)
                if oracle.solve(child) * (1 if us else -1) == value:
                    options[frozenset(action)] = expect(child, depth)
            result = EndgameSolver(cards, trump, swindle_depth=depth).solve(
                controller._to_move.cards, controller._to_respond.cards, controller.on_table, phase)
            self.assertEqual(result.outcome, value)
            self.assertIn(frozenset(result.cards), options)
            if value == 1 or len(options) == 1:
                self.assertIsNone(result.expected_vs_random)
            else:
                self.assertEqual(options[frozenset(result.cards)], max(options.values()))
                self.assertAlmostEqual(result.expected_vs_random, float(max(options.values())))
                checked.add(phase)
        self.assertEqual(checked, {'move', 'respond', 'give_more'})

    def test_invalid_positions_rejected(self):
        solver = EndgameSolver(['6C', '7C'], '6S')
        with self.assertRaises(ValueError):
            solver.solve(['6C'], ['6C'])
        with self.assertRaises(ValueError):
            solver.solve(['6C', '6C'], ['7C'])
        with self.assertRaises(ValueError):
            solver.solve(['6C'], ['7C'], phase='respond')


class NextGenTest(unittest.TestCase):
    def test_logged_settings_reproduce_swindle_choice(self):
        attacker, defender = ['QC', '9H', 'JC'], ['9S', 'QS', '7D']
        data = game(attacker, defender).get_game_data_for(GameController.PLAYER1)
        choices = []
        for depth in (0, 3):
            with self.subTest(swindle_depth=depth):
                engine = NextGenEngine(swindle_depth=depth, explain_decisions=True)
                engine.init('6S')
                engine.deal(attacker, {})
                chosen = engine.move([], data)
                choices.append(chosen)
                record = json.loads(json.dumps(engine.last_decision))
                self.assertEqual(record['settings']['swindle_depth'], depth)

                replay = NextGenEngine(**record['settings'])
                replay.init(record['trump'])
                replay.deal(record['hand'], {})
                self.assertEqual(replay.move(record['on_table'], record['gamedata']), chosen)
                self.assertEqual(replay.last_solution.outcome, record['outcome'])
                self.assertEqual(replay.last_solution.expected_vs_random, record['expected_vs_random'])
        self.assertEqual(choices, ['9H', 'JC'])

    def test_inference_uses_discarded_and_table_and_removes_chosen_card(self):
        controller = game(['6C'], ['7C'], table=['6D'], phase='responding')
        engine = NextGenEngine()
        engine.init('6S')
        engine.deal(['7C'], {})
        result = engine.respond(controller.on_table,
                                controller.get_game_data_for(controller.PLAYER2))
        self.assertIsNotNone(engine.last_solution)
        self.assertEqual(result, '')  # cannot beat diamonds with clubs
        self.assertEqual(engine._cards, {DurakCard('7C')})

    def test_missing_or_inconsistent_data_uses_dummy(self):
        for data in ({}, {'deck_count': 5}, {'deck_count': 0},
                     {'deck_count': 0, 'enemy_count': 1, 'discarded': []}):
            engine = NextGenEngine()
            dummy = DummyEngine()
            for player in (engine, dummy):
                player.init('6S')
                player.deal(['6C', '7C'], {})
            self.assertEqual(str(engine.move([], data)), str(dummy.move([], data)))
            self.assertIsNone(engine.last_solution)
            self.assertIsNotNone(engine.fallback_reason)
            self.assertEqual(engine._cards, dummy._cards)

    def test_card_and_node_limits_fall_back_without_mutating_hand_during_search(self):
        controller = game(['6C', '8C'], ['7C', '9C'])
        for options in ({'max_cards': 2}, {'max_nodes': 1}):
            engine = NextGenEngine(explain_decisions=True, **options)
            engine.init('6S')
            engine.deal(['6C', '8C'], {})
            played = DurakCard(str(engine.move([], controller.get_game_data_for(controller.PLAYER1))))
            self.assertIn(played, controller._player1.cards)
            self.assertEqual(engine._cards, controller._player1.cards - {played})
            self.assertIsNone(engine.last_solution)
            self.assertIn('reached', engine.fallback_reason)
            self.assertEqual(engine.last_decision['model'], 'analytic_exchange')

    def test_new_game_resets_solver(self):
        engine = NextGenEngine()
        engine.init('6S')
        engine.deal(['6C'], {})
        engine.move([], game(['6C'], ['7C']).get_game_data_for(GameController.PLAYER1))
        self.assertIsNotNone(engine._solver)
        engine.init('6H')
        self.assertIsNone(engine._solver)
        self.assertIsNone(engine.last_solution)
        self.assertFalse(engine._cards)

    def test_protocol_subprocess_and_clean_eof_without_gui(self):
        controller = game(['6C'], ['7C'])
        data = json.dumps(controller.get_game_data_for(controller.PLAYER1))
        commands = 'init 6S\ndeal 6C\nmove ## ' + data + '\n'
        for ending in ('', 'game_end\n'):
            process = subprocess.run([sys.executable, '-m', 'durak.engine.nextgen'],
                                     input=commands + ending, capture_output=True,
                                     text=True, timeout=10, check=True)
            self.assertEqual(process.stdout, 'ok\nok\n6C\n')
            self.assertEqual(process.stderr, '')

    def test_complete_headless_games_against_dummy_and_self(self):
        for seed in range(12):
            controller = GameController()
            controller._logger_enabled = False
            with patch('durak.controller.random', Random(seed)):
                data = controller.start_new_game()
            engines = [NextGenEngine(), DummyEngine() if seed % 2 else NextGenEngine()]
            for index, engine in enumerate(engines, 1):
                engine.init(data['trump'])
                engine.deal(data['player%d_cards' % index], {})
            for _ in range(500):
                if controller.is_game_over():
                    break
                if controller.state == controller.States.DEALING:
                    dealt = controller.deal()
                    for index, engine in enumerate(engines, 1):
                        engine.deal(dealt['player%d_cards' % index], {})
                else:
                    phase = PHASES[controller.state]
                    index = int(not controller.is_player1_to_move()) ^ (phase == 'respond')
                    engine = engines[index]
                    output = getattr(engine, phase)(controller.on_table,
                        controller.get_game_data_for(controller.PLAYER1 if index == 0 else controller.PLAYER2))
                    cards = tuple(map(DurakCard, str(output).split()))
                    getattr(controller, 'register_' + ('response' if phase == 'respond' else phase))(
                        cards if phase == 'give_more' else (cards[0] if cards else None))
                self.assertEqual(engines[0]._cards, controller._player1.cards)
                self.assertEqual(engines[1]._cards, controller._player2.cards)
            else:
                self.fail('Headless game did not finish')
