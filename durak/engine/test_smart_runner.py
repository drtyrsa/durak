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
from durak.engine.smart_runner import SmartRunnerEngine
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


class EngineTest(unittest.TestCase):
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
