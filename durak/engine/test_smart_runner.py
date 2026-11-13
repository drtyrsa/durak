"""Smart Runner: simulator fidelity against GameController, tracking, engine play."""
from random import Random
import json
import unittest
from unittest.mock import patch

from durak.controller import GameController, Table
from durak.engine.dummy import DummyEngine
from durak.engine.matchup import DealRandom, play_game
from durak.engine.nextgen import NextGenEngine
from durak.engine.simulator import GIVE, MOVE, RESPOND, STOPPED, Universe, defence, pickup, rollout
from durak.engine.smart_runner import SmartRunnerEngine, _LeafSearch, _LeafValue, _Prediction
from durak.engine.test_nextgen import game
from durak.utils.cards import CardSet, DurakCard

PHASES = {'moving': 'move', 'responding': 'respond', 'giving_more': 'give_more'}


def value(card, trump):
    return (card.suit == trump.suit, card.numeric_rank, DurakCard.SUITS.index(card.suit))


def policy(controller, careful=0):
    """The simulator's rollout policy, written against the controller API."""
    trump = controller._trump
    phase = PHASES[controller.state]
    attacker, defender = controller._to_move.cards, controller._to_respond.cards
    table = controller.on_table
    if phase == 'respond':
        options = [c for c in defender if c in defender.cards_that_can_beat(table[-1])]
        if not options:
            return ()
        card = min(options, key=lambda c: value(c, trump))
        defender_seat = int(controller.is_player1_to_move())
        if (careful & (1 << defender_seat) and controller.deck_count > 4
                and card.suit == trump.suit and len(set(defender) | set(table)) <= 9
                and len(table) <= 3
                and (card.rank in 'JQKA' or (len(table) == 1 and table[-1].rank in 'QKA'))):
            return ()
        return (card,)
    options = sorted(attacker.cards_that_can_be_added_to(table), key=lambda c: value(c, trump))
    plain = [c for c in options if c.suit != trump.suit]
    if phase == 'move':
        if not table:
            return ((plain or options)[0],)
        options = plain if controller.deck_count else options
        return tuple(options[:1])
    options = plain if controller.deck_count else options
    return tuple(options[:len(defender) - 1])


def apply(controller, action):
    phase = PHASES[controller.state]
    register = getattr(controller, 'register_' + ('response' if phase == 'respond' else phase))
    register(action if phase == 'give_more' else (action[0] if action else None))
    if controller.state == controller.States.DEALING:
        controller.deal()


def legal(controller):
    phase = PHASES[controller.state]
    attacker, defender = controller._to_move.cards, controller._to_respond.cards
    table = controller.on_table
    if phase == 'respond':
        return [(c,) for c in defender.cards_that_can_beat(table[-1])] + [()]
    options = attacker.cards_that_can_be_added_to(table)
    if phase == 'move':
        return [(c,) for c in options] + ([()] if table else [])
    options = sorted(options, key=lambda c: value(c, controller._trump))[:len(defender) - 1]
    return [tuple(options[:k]) for k in range(len(options) + 1)]


def clone(controller):
    result = GameController()
    result._logger_enabled = False
    result._trump = controller._trump
    result._deck = list(controller._deck)
    result._discarded = list(controller._discarded)
    for mine, theirs in ((result._player1, controller._player1),
                         (result._player2, controller._player2)):
        mine.cards = CardSet(theirs.cards, controller._trump)
    result._to_move = (result._player1 if controller.is_player1_to_move() else result._player2)
    result._on_table = Table(controller._on_table)
    result._on_table.given_more = set(controller._on_table.given_more)
    result._state = controller._state
    result._no_response = controller._no_response
    return result


def simulate(controller, action, careful=0, split=False):
    """Winner seat (0 = player1) from the bit-mask simulator."""
    u = Universe(controller._trump)
    phase = PHASES[controller.state]
    attacker = 0 if controller.is_player1_to_move() else 1
    table = controller.on_table
    pending = u.bit[table[-1]] if phase == 'respond' else 0
    hands = [u.mask(controller._player1.cards), u.mask(controller._player2.cards)]
    deck = [u.bit[c] for c in reversed(controller._deck)]
    mode = {'move': MOVE, 'respond': RESPOND, 'give_more': GIVE}[phase]
    result = rollout(u, hands, deck, attacker, u.mask(table), pending, mode, u.mask(action),
                     careful=careful, stop_at_empty=split)
    if result >= STOPPED:
        result = rollout(u, hands, deck, result - STOPPED, 0, 0, MOVE, careful=careful)
    return {0: 'player1', 1: 'player2', -1: None}[result]


class SimulatorTest(unittest.TestCase):
    def test_pickup_refill_and_trump_destination_match_controller(self):
        u = Universe('TD')
        for defender in (['7D', '7S'], ['7D', '7S', '8D', '9H', 'KH', 'QD']):
            for given in ([], ['8S']):
                controller = game(['8S', 'TH', 'AD'], defender, trump='TD',
                                  table=['8H'], phase='giving_more')
                controller._deck = list(map(DurakCard, ['JS', '6D', 'TD']))
                hands = [u.mask(controller._player1.cards), u.mask(controller._player2.cards)]
                deck = [u.bit[c] for c in reversed(controller._deck)]
                result = pickup(hands, deck, 0, u.mask(controller.on_table), u.mask(given))
                apply(controller, tuple(map(DurakCard, given)))
                self.assertIsNone(result)
                self.assertEqual(hands, [u.mask(controller._player1.cards),
                                         u.mask(controller._player2.cards)])
                self.assertEqual(deck, [u.bit[c] for c in reversed(controller._deck)])

    def test_selective_pickups_save_trumps_without_ignoring_pickup_cost(self):
        u = Universe('9S')
        hand = u.mask(['AS', '6D', '8D'])
        attack = u.mask(['QS'])
        ace = u.mask(['AS'])
        self.assertEqual(defence(u, hand, attack, attack, 12, careful=True), 0)
        self.assertEqual(defence(u, hand, attack, attack, 12), ace)
        self.assertEqual(defence(u, hand, attack, attack, 4, careful=True), ace)
        table = u.mask(['6H', '7H', '8C', 'JC', 'QS'])
        self.assertEqual(defence(u, hand, attack, table, 12, careful=True), ace)
        hand = u.mask(['AS', '6D', '7D', '8D', '9D', 'TD', 'JD', 'QD', 'KD'])
        self.assertEqual(defence(u, hand, attack, attack, 12, careful=True), ace)

    def test_rollouts_match_controller_from_random_positions(self):
        rng = Random(4)
        phases, endings = set(), set()
        for seed in range(150):
            controller = GameController()
            controller._logger_enabled = False
            with patch('durak.controller.random', DealRandom(seed)):
                controller.start_new_game()
            for _ in range(rng.randrange(80)):
                if controller.is_game_over():
                    break
                apply(controller, rng.choice(legal(controller)))
            if controller.is_game_over():
                continue
            phases.add((PHASES[controller.state], controller.deck_count == 0))
            for careful in (0, 1, 2, 3):
                for action in legal(controller):
                    reference = clone(controller)
                    apply(reference, action)
                    while not reference.is_game_over():
                        apply(reference, policy(reference, careful))
                    endings.add(reference.winner)
                    self.assertEqual(simulate(controller, action, careful), reference.winner,
                                     (seed, action, careful))
                    self.assertEqual(simulate(controller, action, careful, split=True),
                                     reference.winner, (seed, action, careful, 'resume'))
        self.assertEqual({p for p, _ in phases}, {'move', 'respond', 'give_more'})
        self.assertEqual({empty for _, empty in phases}, {True, False})
        self.assertEqual(endings, {'player1', 'player2', None})


class TrackingTest(unittest.TestCase):
    def test_known_opponent_cards_match_real_hands(self):
        learned = 0
        for seed in range(30):
            controller = GameController()
            controller._logger_enabled = False
            with patch('durak.controller.random', DealRandom(seed)):
                data = controller.start_new_game()
            engines = [SmartRunnerEngine(worlds=4, leaf_deck=0), DummyEngine()]
            players = (controller.PLAYER1, controller.PLAYER2)
            for index, engine in enumerate(engines):
                engine.init(data['trump'])
                engine.deal(data['player%d_cards' % (index + 1)],
                            controller.get_game_data_for(players[index]))
            while not controller.is_game_over():
                if controller.state == controller.States.DEALING:
                    dealt = controller.deal()
                    for index, engine in enumerate(engines):
                        engine.deal(dealt['player%d_cards' % (index + 1)],
                                    controller.get_game_data_for(players[index]))
                else:
                    phase = PHASES[controller.state]
                    index = int(not controller.is_player1_to_move()) ^ (phase == 'respond')
                    output = getattr(engines[index], phase)(
                        controller.on_table, controller.get_game_data_for(players[index]))
                    cards = tuple(map(DurakCard, str(output).split()))
                    register = getattr(controller, 'register_' + (
                        'response' if phase == 'respond' else phase))
                    register(cards if phase == 'give_more' else (cards[0] if cards else None))
                    if index:
                        continue
                # Check where the engine has just observed: after deals and
                # its own decisions (its played cards are still on the table).
                engine, enemy = engines[0], set(controller._player2.cards)
                known = engine._enemy - set(controller.on_table)
                self.assertLessEqual(known, enemy, seed)
                learned = max(learned, len(known))
        self.assertGreater(learned, 0)

    def test_taking_keeps_beating_cards_possible_and_remembers_pickup(self):
        engine = SmartRunnerEngine(worlds=64, leaf_deck=0, race=False)
        engine.init('6S')
        data = {'enemy_count': 6, 'deck_count': 24, 'discarded': []}
        # We attacked with 6C; the opponent takes, possibly while holding AC.
        engine.deal(['6D', '8H', '9D', 'JH', 'QD'], data)
        sampled_hands = []

        def sample(u, hands, deck, attacker, table, pending, mode, forced=None, **kwargs):
            sampled_hands.append(u.unpack(hands[1]))
            return 0 if forced == 0 else 1  # choose no throw-ins for this tracking scenario

        with patch('durak.engine.smart_runner.rollout', side_effect=sample):
            self.assertEqual(engine.give_more(['6C'], data), '')
        self.assertTrue(any(DurakCard('AC') in hand for hand in sampled_hands))

        data = dict(data, enemy_count=7, deck_count=23)
        engine.deal(['7D'], data)
        self.assertEqual(engine._enemy, {DurakCard('6C')})
        sampled_hands.clear()
        with patch('durak.engine.smart_runner.rollout', side_effect=sample):
            engine.move([], data)
        self.assertTrue(any(DurakCard('AC') in hand for hand in sampled_hands))
        self.assertTrue(all(DurakCard('6C') in hand for hand in sampled_hands))


class SharedLeafTest(unittest.TestCase):
    def test_enumeration_covers_each_hidden_arrangement_and_both_styles(self):
        pool, known, bottom = [1 << i for i in range(7)], 1 << 7, 1 << 8
        schedule, trials, possible, complete = SmartRunnerEngine._worlds(
            pool, 5, known, bottom, 128, Random(9), True)
        rows = list(schedule)
        self.assertEqual((len(rows), trials, possible, complete), (84, 84, 42, True))
        arrangements = {}
        for enemy, deck, careful, reply_weight in rows:
            self.assertEqual(enemy.bit_count(), 6)
            self.assertTrue(enemy & known)
            self.assertEqual(deck[0], bottom)
            self.assertEqual(enemy & sum(deck), 0)
            self.assertEqual(enemy | sum(deck), sum(pool) | known | bottom)
            arrangements.setdefault((enemy, tuple(deck)), []).append((careful, reply_weight))
        self.assertEqual(len(arrangements), 42)
        self.assertTrue(all(styles == [(3, 0), (0, .5)] for styles in arrangements.values()))
        self.assertEqual(sum(row[3] for row in rows) / len(rows), .25)
        again, *_ = SmartRunnerEngine._worlds(pool, 5, known, bottom, 128, Random(9), True)
        self.assertEqual(rows, list(again))

    def test_large_world_sets_still_sample_with_original_policy_weights(self):
        for limit, enabled in ((83, True), (128, False)):
            schedule, trials, possible, complete = SmartRunnerEngine._worlds(
                [1 << i for i in range(7)], 5, 128, 256, limit, Random(9), enabled)
            rows = list(schedule)
            self.assertEqual((trials, possible, complete), (limit, 42, False))
            self.assertEqual(len(rows), limit)
            self.assertEqual([r[2:] for r in rows[:4]], [(3, 0), (0, 0), (3, 0), (0, 1)])

    def test_complete_world_scores_do_not_use_sampling_uncertainty_tie_break(self):
        engine = SmartRunnerEngine()
        values = [[1] * 100, [1] * 99 + [-1]]
        self.assertEqual(engine._select([0, 1], values, [2, 0])[0], 1)
        self.assertEqual(engine._select([0, 1], values, [2, 0], complete=True)[0], 0)

    def test_proofs_update_old_predictions_and_the_opponents_reply(self):
        leaf = _LeafValue((1, 2), 1)
        normal = _Prediction(leaf, 3)
        defended = normal.with_reply(_Prediction(0, 2), .5)
        other_seat = _Prediction(leaf, -3, -1)
        self.assertEqual(defended.resolve(), (.5, 2.5))
        leaf.value, leaf.exact = -1, True
        self.assertEqual(normal.resolve(), (-1, 3))
        self.assertEqual(defended.resolve(), (-1, 3))
        self.assertEqual(other_seat.resolve(), (1, -3))
        plan, outcomes = SmartRunnerEngine._worst_pickup_plan(
            [_Prediction(0, 0).resolve()], {'known attack': [normal.resolve()]})
        self.assertEqual((plan, outcomes), ('known attack', [(-1, 3)]))

    def test_cache_reuses_proven_draw_even_without_budget_and_resets_for_new_game(self):
        engine = SmartRunnerEngine()
        engine.init('6S')
        u = engine._universe
        hands = [u.mask(['6C']), u.mask(['7C'])]
        search = _LeafSearch(engine, hands[0] | hands[1])
        leaf = search.register(hands, 0)
        self.assertIs(leaf, search.register(hands[::-1], 1))
        search.refine()
        self.assertTrue(leaf.exact)
        self.assertEqual(leaf.value, 0)
        engine.leaf_budget = 0
        reused = _LeafSearch(engine, hands[0] | hands[1])
        with patch('durak.engine.smart_runner.rollout', side_effect=AssertionError('cached')):
            hit = reused.register(hands, 0)
            reused.refine()
        self.assertEqual((hit.exact, hit.value, reused.nodes), (True, 0, 0))
        self.assertEqual(reused.diagnostics()['leaf_cache_hits'], 1)
        engine.init('6H')
        self.assertEqual(engine._leaf_values, {})

    def test_budget_is_strict_and_failed_searches_never_poison_exact_cache(self):
        engine = SmartRunnerEngine(leaf_budget=7, leaf_nodes=4)
        engine.init('6S')
        u = engine._universe
        hands = [u.mask(['6C', '8C', 'TC']), u.mask(['7C', '9C', 'JC'])]
        search = _LeafSearch(engine, hands[0] | hands[1])
        for attacker in (0, 1):
            search.register(hands, attacker)
        search.refine()
        self.assertEqual(search.nodes, 7)
        self.assertTrue(all(leaf.nodes <= 4 for leaf in search.states.values()))
        self.assertEqual(search.diagnostics()['leaf_fallbacks'], 2)
        self.assertEqual(engine._leaf_values, {})


class ReservePickupTest(unittest.TestCase):
    def setUp(self):
        self.engine = SmartRunnerEngine(worlds=16, leaf_worlds=16, explain_decisions=True)
        self.engine.init('TH')
        self.u = self.engine._universe
        self.hand = '9C TS JS QC KH'.split()
        self.table = '7D KD KC'.split()
        self.unseen = '6H 8H QD AC 9S QH 8C AD 7S 7C 9D AS 7H AH JC'.split()

    def context(self, hand=None, table=None, known=(), unseen=None, slots=4, deck=12):
        table = self.table if table is None else table
        return self.engine._reserve_pickup(
            'respond', self.u.mask(self.hand if hand is None else hand), self.u.mask(table),
            self.u.mask(table[-1:]), self.u.mask(known),
            self.u.mask(self.unseen if unseen is None else unseen), slots, deck)

    def data(self):
        live = set(map(DurakCard, self.hand + self.table + self.unseen + ['TH']))
        return {'deck_count': 12, 'enemy_count': 4,
                'discarded': list(map(str, DurakCard.all() - live))}

    def test_useful_pickup_restores_plain_answers_and_counts_possible_throw_ins(self):
        result = self.context()
        self.assertEqual(result['trump'], 'KH')
        self.assertEqual(result['new_plain_covers'], ['9D', 'QD'])
        self.assertEqual(result['hand_after_take'], 8)
        self.assertAlmostEqual(result['throw_in_allowance'], .8)
        self.assertEqual(result['score_gap_limit'], .2)
        # Removing one newly answerable card from the live set reduces the
        # strategic allowance; removing both makes this pickup unhelpful.
        unseen = [c for c in self.unseen if c != '9D']
        self.assertEqual(self.context(unseen=unseen, deck=11)['score_gap_limit'], .1)
        self.assertIsNone(self.context(unseen=[c for c in unseen if c != 'QD'], deck=10))

    def test_no_preference_with_other_defences_or_an_unmanageable_pickup(self):
        for changes in (
                {'hand': '9C TS JS AC KH'.split()},  # plain answer to KC
                {'hand': '9C JH JS QC KH'.split()},  # another trump remains
                {'hand': self.hand + ['8S']},       # already too many cards
                {'hand': '9C TS JS QC AH'.split(), 'table': '7D KD KH'.split()},
                {'deck': 5}, {'deck': 0}, {'deck': 24},
                {'slots': 10, 'deck': 6},           # many possible throw-ins
                {'known': ['7C', '7S'], 'slots': 2,
                 'unseen': [c for c in self.unseen if c not in ('7C', '7S')]}):
            with self.subTest(changes=changes):
                self.assertIsNone(self.context(**changes))

    def test_prior_is_bounded_and_never_overrides_a_simulated_win(self):
        # Each candidate receives 16 trials; return controlled terminal
        # outcomes so we test selection without any hidden search assumptions.
        for trump_wins, pickup_wins, expected in ((8, 7, ''), (8, 4, 'KH'), (16, 15, 'KH')):
            with self.subTest(trump_wins=trump_wins, pickup_wins=pickup_wins):
                engine = SmartRunnerEngine(worlds=16, leaf_worlds=16, explain_decisions=True)
                engine.init('TH'); engine.deal(self.hand, self.data())
                counts = {0: 0, self.u.mask(['KH']): 0}

                def controlled(u, hands, deck, attacker, table, pending, mode, forced=None, **kw):
                    counts[forced] += 1
                    wins = trump_wins if forced else pickup_wins
                    return 0 if counts[forced] <= wins else 1

                with patch('durak.engine.smart_runner.rollout', side_effect=controlled):
                    self.assertEqual(engine.respond(self.table, self.data()), expected)
                self.assertEqual(set(counts.values()), {16})
                self.assertEqual(engine.last_decision['reserve_pickup']['used'], expected == '')

    def test_audited_last_trump_is_saved_with_default_search_limits(self):
        engine = SmartRunnerEngine(explain_decisions=True)
        engine.init('TH'); engine.deal(self.hand, self.data())
        self.assertEqual(engine.respond(self.table, self.data()), '')
        info = engine.last_decision
        self.assertEqual(info['selection'], 'reserve')
        self.assertEqual(info['score_leader'], ['KH'])
        self.assertLessEqual(info['leaf_nodes_used'], engine.leaf_budget)
        self.assertEqual(info['reserve_pickup']['new_plain_covers'], ['9D', 'QD'])


class EngineTest(unittest.TestCase):
    def test_small_hidden_set_reuses_exact_leaves_in_low_luck_dummy_loss(self):
        # Seed 202617093, action 34. Previously 128 sampled trials repeatedly
        # solved the same leaves, spent >500k nodes and chose the trump jack.
        hand = '7C 8D 8S TC JD JH JS QS KH'.split()
        hidden = 'TH QD KC KD AC 6H 6C QH'.split()
        live = set(map(DurakCard, hand + hidden + ['6S']))
        data = {'enemy_count': 5, 'deck_count': 3,
                'discarded': list(map(str, DurakCard.all() - live))}
        engine = SmartRunnerEngine(explain_decisions=True)
        engine.init('QH')
        engine.deal(hand, data)
        self.assertEqual(engine.respond(['6S'], data), '8S')
        info = engine.last_decision
        self.assertEqual((info['sampling'], info['hidden_worlds'], info['worlds']),
                         ('enumerated', 42, 84))
        self.assertTrue(all(c['worlds'] == 84 for c in info['candidates']))
        self.assertLess(info['leaf_nodes_used'], engine.leaf_budget)
        self.assertLess(info['leaf_unique_positions'], info['leaf_evaluations'])
        self.assertGreater(info['leaf_exact_evaluations'], info['leaf_fallbacks'])

    def test_eight_card_stock_uses_exact_leaves_before_a_long_attack_empties_it(self):
        # Seed 202614065, before the four-card attack that emptied an eight-card
        # stock. Revision 3 chose KH using exclusively greedy endgames.
        hand = list(map(DurakCard, '7C 7D KD KH KS AD'.split()))
        hidden = set(map(DurakCard, '8C 8S TS QC AH AS AC QH 6H 8H 9C TD 7S JC'.split()))
        data = {'enemy_count': 6, 'deck_count': 8,
                'discarded': list(map(str, DurakCard.all() - set(hand) - hidden))}
        engine = SmartRunnerEngine(explain_decisions=True)
        engine.init('JC')
        engine.deal(hand, data)
        self.assertEqual(str(engine.move([], data)), '7D')
        self.assertGreater(engine.last_decision['exact_worlds'], 0)
        self.assertGreater(engine.last_decision['leaf_nodes_used'], 0)

    def test_complete_games_against_dummy_and_nextgen(self):
        for seed in range(4):
            for opponent in (DummyEngine(), NextGenEngine()):
                for engines in ((SmartRunnerEngine(worlds=8, leaf_deck=0), opponent),
                                (opponent, SmartRunnerEngine(worlds=8, leaf_deck=0))):
                    play_game(*engines, seed)

    def test_explained_decisions_are_json_and_use_every_strategy(self):
        engine = SmartRunnerEngine(worlds=160, min_worlds=64, leaf_worlds=16, leaf_budget=20_000,
                                   explain_decisions=True)
        strategies = set()
        original = engine._decide

        def decide(*args):
            result = original(*args)
            json.dumps(engine.last_decision)
            strategies.add(engine.last_decision['strategy'])
            if engine.last_decision.get('exact_worlds'):
                strategies.add('exact_leaves')
            if any(c['worlds'] < engine.last_decision['worlds']
                   for c in engine.last_decision.get('candidates', ())):
                strategies.add('raced')
            return result

        engine._decide = decide
        for seed in range(4):
            play_game(engine, DummyEngine(), seed)
        self.assertLessEqual({'monte_carlo', 'exact', 'exact_leaves', 'raced'}, strategies)

    def test_race_drops_only_clearly_worse_candidates(self):
        engine = SmartRunnerEngine(z=3.0)
        good, close, bad = [1] * 100, [1] * 95 + [-1] * 5, [-1] * 100
        self.assertEqual(engine._race([0, 1, 2], [good, close, bad]), [0, 1])
        self.assertEqual(engine._race([0, 1], [good, good]), [0, 1])

    def test_conservation_only_breaks_small_uncertain_differences(self):
        engine = SmartRunnerEngine()
        best = [1] * 100
        close = [1] * 99 + [-1]
        bad = [1] * 90 + [-1] * 10
        chosen, leader, _ = engine._select([0, 1], [best, close], [2, 0])
        self.assertEqual((chosen, leader), (1, 0))
        chosen, _, _ = engine._select([0, 1], [best, bad], [2, 0])
        self.assertEqual(chosen, 0)
        # Correlated outcomes are not uncertain merely because both vary.
        noisy = [-1, 1] * 50
        chosen, _, _ = engine._select([0, 1], [noisy, [v - .01 for v in noisy]], [2, 0])
        self.assertEqual(chosen, 0)

    def test_losing_ties_use_resistance_without_overriding_better_outcomes(self):
        engine = SmartRunnerEngine()
        results = [[-1] * 128 for _ in range(3)]
        costs, resistance = [1.6, 2.5, .9], [2, -3, -.6]
        self.assertEqual(engine._select([0, 1, 2], results, costs, resistance)[0], 0)
        results[1] = [0] * 128  # a draw takes priority over a prettier hand
        self.assertEqual(engine._select([0, 1, 2], results, costs, resistance)[0], 1)
        engine.init('TD')
        u = engine._universe
        self.assertGreater(engine._resistance([u.mask(['7C']), 0], 0),
                           engine._resistance([u.mask(['7C', '8C']), 0], 0))

    def test_pickup_plan_cannot_choose_a_different_reply_for_each_deck(self):
        normal = [(1, 0), (1, 0)]
        plans = {('hold', 1): [(-1, 0), (1, 0)],
                 ('cheap', 2): [(1, 0), (-1, 0)]}
        plan, outcomes = SmartRunnerEngine._worst_pickup_plan(normal, plans)
        self.assertIn(plan, plans)
        self.assertEqual(sum(score for score, _ in outcomes), 0)
        # Picking a different plan with advance knowledge of each deck would
        # incorrectly score the pickup as a loss in both worlds.
        self.assertNotEqual(outcomes, [(-1, 0), (-1, 0)])

    def test_pickup_probes_keep_throw_ins_optional_and_only_lead_known_cards(self):
        engine = SmartRunnerEngine()
        engine.init('TD')
        u = engine._universe
        mine = u.mask(['7D', '7S', '8D', '9H', 'KH', 'QD'])
        enemy = u.mask(['8S', 'TH', 'AD'])
        deck = [u.bit[DurakCard(c)] for c in ['TD', '6D', 'JS']]
        original_deck = deck[:]
        replies = list(engine._pickup_replies(mine, enemy, deck, u.mask(['8H']), u.mask(['TH'])))
        self.assertEqual(len(replies), 2)
        self.assertEqual({plan[1] for plan, _, _ in replies}, {u.mask(['TH'])})
        self.assertEqual({bool(hands[0] & u.mask(['8S'])) for _, hands, _ in replies}, {False, True})
        for plan, hands, remaining in replies:
            self.assertTrue(hands[0] & u.mask(['8H']))
            self.assertTrue(hands[1] & plan[1])
            self.assertFalse(hands[0] & hands[1])
        self.assertEqual(deck, original_deck)
        self.assertEqual(list(engine._pickup_replies(mine, enemy, deck, u.mask(['8H']), 0)), [])

    def test_pickup_checks_known_followup_in_logged_position(self):
        hand = ['7D', '7S', '8D', '9H', 'KH', 'AD']
        unknown = ['JC', 'JS', 'QS', 'QH', '6D', '9D', 'JD', 'QD', 'TD', '8S']
        live = set(map(DurakCard, hand + unknown + ['8H', 'TH']))
        data = {'deck_count': 5, 'enemy_count': 6,
                'discarded': list(map(str, DurakCard.all() - live))}
        engine = SmartRunnerEngine(worlds=512, explain_decisions=True)
        engine.init('TD')
        engine.deal(hand, data)
        engine._enemy = {DurakCard('TH')}
        self.assertIn(engine.respond(['8H'], data), ('9H', 'KH'))
        info = engine.last_decision
        self.assertEqual(info['pickup_threats'], ['TH'])
        self.assertGreater(info['pickup_checks'], 0)
        take = next(c for c in info['candidates'] if not c['cards'])
        self.assertLess(take['score'], take['continuation_score'])

    def test_late_losing_pickup_prefers_a_fighting_hand(self):
        hand = ['7D', '7S', '8D', '8S', '9H', 'AD']
        unseen = ['6D', 'JD', 'JS', 'QD', 'QS', 'QH', 'TD']
        live = set(map(DurakCard, hand + unseen + ['JC']))
        data = {'deck_count': 2, 'enemy_count': 5,
                'discarded': list(map(str, DurakCard.all() - live))}
        engine = SmartRunnerEngine(explain_decisions=True)
        engine.init('TD')
        engine.deal(hand, data)
        self.assertEqual(engine.respond(['JC'], data), '7D')
        self.assertEqual(engine.last_decision['selection'], 'resistance')
        self.assertTrue(all(c['score'] == -1 for c in engine.last_decision['candidates']))

    def test_attack_checks_opponents_voluntary_pickup(self):
        engine = SmartRunnerEngine(worlds=8, leaf_deck=0, race=False, explain_decisions=True)
        engine.init('9S')
        live = set(map(DurakCard, ['7S', '7D', 'KS', 'AD', '9S']))
        data = {'deck_count': 1, 'enemy_count': 2,
                'discarded': list(map(str, DurakCard.all() - live))}
        engine.deal(['7S', '7D'], data)
        engine._enemy = set(map(DurakCard, ['KS', 'AD']))
        replies = []

        def evaluate(u, hands, deck, attacker, table, pending, mode, forced=None, **kwargs):
            if mode == RESPOND:
                replies.append((u.unpack(table), forced))
                return 1  # taking defeats an apparently winning trump attack
            return 0

        with patch('durak.engine.smart_runner.rollout', side_effect=evaluate):
            self.assertEqual(engine.move([], data), '7D')
        self.assertEqual(replies, [([DurakCard('7S')], 0)] * 2)
        self.assertEqual(engine.last_decision['reply_checks'], 2)
        self.assertEqual(engine.last_decision['selection'], 'score')

    def test_larger_endgame_uses_exact_search_and_reports_budget_failure(self):
        # The game's 14-card position: a cheap rollout says win, exact play says loss.
        hand = ['7C', '8S', '9S', 'TD', 'TH', 'KH']
        enemy = ['7S', 'JS', 'QH', 'KC', 'KS', 'AH', 'AS']
        live = set(map(DurakCard, hand + enemy + ['6S']))
        data = {'deck_count': 0, 'enemy_count': len(enemy),
                'discarded': list(map(str, DurakCard.all() - live))}
        for budget, strategy in ((500_000, 'exact'), (1, 'monte_carlo')):
            engine = SmartRunnerEngine(max_nodes=budget, explain_decisions=True)
            engine.init('9S')
            engine.deal(hand, data)
            engine.respond(['6S'], data)
            info = engine.last_decision
            self.assertEqual(info['strategy'], strategy)
            self.assertEqual(info['exact_search']['live_cards'], 14)
            if strategy == 'exact':
                self.assertEqual(info['outcome'], -1)
            else:
                self.assertEqual(info['exact_search'],
                                 {'status': 'node_limit', 'live_cards': 14, 'nodes': 1})

    def test_falls_back_to_dummy_without_game_data(self):
        engine, dummy = SmartRunnerEngine(), DummyEngine()
        for player in (engine, dummy):
            player.init('6S')
            player.deal(['6C', '7C'], {})
        self.assertEqual(engine.move([], {}), str(dummy.move([], {})))
        self.assertEqual(engine._cards, dummy._cards)


if __name__ == '__main__':
    unittest.main()
