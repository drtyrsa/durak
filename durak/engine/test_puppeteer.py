"""Puppeteer: rollout hook safety, profile learning, engine play, determinism."""
import json
from random import Random
import unittest
from unittest.mock import patch

from durak.engine.dummy import DummyEngine
from durak.engine.matchup import play_game
from durak.engine.nextgen import NextGenEngine
from durak.engine.puppeteer import OpponentProfile, PuppeteerEngine
from durak.engine.simulator import DRAW, GIVE, MOVE, RESPOND, Universe, rollout
from durak.engine.test_nextgen import game
from durak.utils.cards import CardSet, DurakCard


class AlwaysTake(DummyEngine):
    """A pathological opponent: refuses to beat anything."""

    def respond(self, on_table, gamedata):
        return ''


class RecordingEngine(PuppeteerEngine):
    """Puppeteer that snapshots every decision, for reproducibility checks."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.plays = []

    def _decide(self, phase, on_table, gamedata):
        result = super()._decide(phase, on_table, gamedata)
        self.plays.append((phase, tuple(on_table), result,
                           None if self.last_decision is None else dict(self.last_decision)))
        return result


def run_game(engine, opponent, seed):
    """Play one validated game and return the winner seat, or None for a draw."""
    return play_game(engine, opponent, seed)


class SimulatorHookTest(unittest.TestCase):
    def setUp(self):
        self.u = Universe('6S')

    def position(self):
        # Seat 0 leads; the deck has three cards left, trump 6S at the bottom.
        hands = [self.u.mask(['6D', '8H', '8D', '7C']), self.u.mask(['7S', '9H', 'TD', '6C'])]
        deck = [self.u.bit[DurakCard(c)] for c in ('6S', 'KD', 'TH')]
        return hands, deck

    def test_hook_returning_none_matches_the_builtin_rollout(self):
        for seed in range(10):
            hands, deck = self.position()
            builtin = rollout(self.u, [h for h in hands], deck[:], 0, 0, 0, MOVE,
                              forced=self.u.bit[DurakCard('6D')])
            hands, deck = self.position()
            hooked = rollout(self.u, [h for h in hands], deck[:], 0, 0, 0, MOVE,
                             forced=self.u.bit[DurakCard('6D')], policy=lambda *args: None)
            self.assertEqual(builtin, hooked, seed)

    def test_hook_decisions_change_the_game(self):
        # Empty deck, 7C7D versus 8C8S: beating everything ends in a draw,
        # while a defender who always takes hands the attacker the game.
        hands = [self.u.mask(['7C', '7D']), self.u.mask(['8C', '8S'])]

        def defender(beats):
            def hook(u, hs, deck, attacker, table, pending, mode):
                if mode != RESPOND:
                    return None
                if not beats:
                    return 0
                options = hs[1 - attacker] & u.beaters[pending.bit_length() - 1]
                return options & -options or 0
            return hook

        eager = rollout(self.u, [h for h in hands], [], 0, 0, 0, MOVE,
                        forced=self.u.bit[DurakCard('7C')], policy=defender(True))
        passive = rollout(self.u, [h for h in hands], [], 0, 0, 0, MOVE,
                           forced=self.u.bit[DurakCard('7C')], policy=defender(False))
        self.assertEqual(eager, DRAW)
        self.assertEqual(passive, 0)

    def test_illegal_hook_actions_raise(self):
        attacks = {
            'pass an empty table': 0,
            'card not in hand': self.u.bit[DurakCard('9S')],
            'rank not on the table': self.u.bit[DurakCard('7C')],
        }
        for message, action in attacks.items():
            hands, deck = self.position()
            with self.assertRaises(ValueError, msg=message):
                rollout(self.u, hands, deck[:], 0, 0, 0, MOVE, forced=None,
                        policy=lambda *args: action)
        hands, deck = self.position()
        with self.assertRaises(ValueError):
            rollout(self.u, hands, deck[:], 0, self.u.bit[DurakCard('6S')], 0, MOVE, forced=None,
                    policy=lambda *args: self.u.bit['8H'])  # does not beat 6S
        hands, deck = self.position()
        with self.assertRaises(ValueError):
            rollout(self.u, hands, deck[:], 0, self.u.mask(['6D', '7C']), 0, MOVE,
                    forced=None,
                    policy=lambda *args: self.u.mask(['6D', '8H', 'TD']))  # not in hand

    def test_hook_throw_ins_are_validated(self):
        hands = [self.u.mask(['7C', '9H']), self.u.mask(['7S'])]
        with self.assertRaises(ValueError):
            rollout(self.u, hands, [], 0, self.u.mask(['6D']), 0, GIVE, forced=None,
                    policy=lambda *args: self.u.bit[DurakCard('7C')])  # empties the defender's hand
        hands = [self.u.mask(['7C', '9H']), self.u.mask(['7S', '8S'])]
        with self.assertRaises(ValueError):
            rollout(self.u, hands, [], 0, self.u.mask(['6D']), 0, GIVE, forced=None,
                    policy=lambda *args: self.u.bit[DurakCard('TD')])  # not the attacker's card


class ProfileTest(unittest.TestCase):
    def small(self, **kwargs):
        return PuppeteerEngine(worlds=16, probe=16, leaf_deck=2, leaf_worlds=4,
                               leaf_nodes=500, leaf_budget=2_000, **kwargs)

    def test_learns_to_defend_from_an_always_beating_opponent(self):
        engine = self.small()
        for seed in range(3):
            run_game(engine, DummyEngine(), seed)
        profile = engine._profile
        self.assertGreater(profile.defence_rate(0), 0.8)
        self.assertGreater(profile.defence_rate(1), 0.7)
        self.assertGreater(profile.defences, 5)

    def test_learns_refusal_from_an_always_taking_opponent(self):
        always_take, dummy = self.small(), self.small()
        for seed in range(3):
            run_game(always_take, AlwaysTake(), seed)
            run_game(dummy, DummyEngine(), seed)
        self.assertLess(always_take._profile.defence_rate(0),
                        dummy._profile.defence_rate(0))
        self.assertLess(always_take._profile.defence_rate(0), 0.75)
        self.assertGreater(always_take._profile.takes, 0)

    def test_take_against_a_known_beater_counts_as_full_refusal(self):
        engine = self.small()
        engine.init('6S')
        engine._enemy = {DurakCard('7C')}
        engine._record_take([DurakCard('6C')], (frozenset(), 5, 6))
        self.assertEqual(engine._profile.declines[0], 1.0)

    def test_priors_start_sane_and_report_is_json(self):
        profile = OpponentProfile()
        self.assertGreater(profile.defence_rate(0), profile.defence_rate(2))
        self.assertLess(profile.lead_trump_rate(), 0.2)
        json.dumps(profile.report())

    def test_only_voluntary_stops_update_the_profile(self):
        # The opponent's 6D already matches the attack; 7D matches only the
        # rank introduced by our defence. Both must count on a voluntary stop.
        for hand, enemy in [(['7C'], ['6D']), (['7C', '8H'], []),
                            (['7C', '8H'], ['6D']), (['7C', '8H'], ['7D']),
                            (['7C', '8H'], ['9D'])]:
            with self.subTest(hand=hand, enemy=enemy):
                controller = game(enemy, hand, table=['6C'], phase='responding')
                controller._deck = list(map(DurakCard, ['9H', 'TH', '6S']))
                controller._discarded = list(set(controller._discarded) - set(controller._deck))
                engine = self.small()
                engine.init('6S')
                engine.deal(hand, controller.get_game_data_for(controller.PLAYER2))
                engine._enemy = set(map(DurakCard, enemy))  # previously observed pickups
                with patch.object(engine, '_search', return_value=[DurakCard('7C')]):
                    response = engine.respond(controller.on_table,
                                              controller.get_game_data_for(controller.PLAYER2))
                controller.register_response(response)
                voluntary = controller.state == controller.States.MOVING
                opportunity = bool(voluntary and controller._player1.cards.cards_that_can_be_added_to(
                    controller.on_table))
                if voluntary:
                    controller.register_move(None)
                else:
                    self.assertEqual(controller.state, controller.States.DEALING)
                dealt = controller.deal()
                engine.deal(dealt['player2_cards'],
                            controller.get_game_data_for(controller.PLAYER2))
                self.assertEqual(engine._profile.stops, float(opportunity))

    def test_throwin_share_uses_defender_capacity_before_availability_cap(self):
        engine = self.small()
        engine.init('6S')
        # There is capacity for five throws, but only one card matches. Learn
        # from the real bout/refill accounting, then predict the same behaviour.
        for _ in range(10):
            controller = game(['6D', 'AH'], ['7D', '8D', '9D', 'TD', 'JD', 'QD'],
                              table=['6C'], phase='responding')
            controller._deck = [DurakCard('6S')]
            controller._discarded.remove(DurakCard('6S'))
            engine._cards = CardSet(controller._player2.cards, '6S')
            engine._enemy = set(controller._player1.cards)
            engine._ledger = []
            with patch.object(engine, '_search', return_value=[]):
                engine.respond(controller.on_table, controller.get_game_data_for(controller.PLAYER2))
            controller.register_response(None)
            controller.register_give_more(['6D'])
            dealt = controller.deal()
            engine.deal(dealt['player2_cards'], controller.get_game_data_for(controller.PLAYER2))
        self.assertEqual(engine._profile.throwin_shares, [1 / 5] * 10)
        u = engine._universe
        hands = [u.mask(['7D', '8D', '9D', 'TD', 'JD', 'QD']), u.mask(['6D', 'AH'])]
        predicted = engine._imitate(u, hands, [u.bit[DurakCard('6S')]], GIVE,
                                    u.mask(['6C']), 0, Random(0))
        self.assertEqual(u.unpack(predicted), [DurakCard('6D')])

    def test_no_throw_opportunity_is_not_evidence_of_restraint(self):
        engine = self.small()
        engine.init('6S')
        for mine, enemy in ((1, 1), (6, 0)):
            take = {'mine': mine, 'enemy': enemy, 'deck': 0, 'k': 1,
                    'table': (DurakCard('6C'),), 'known': frozenset(),
                    'pool': frozenset([DurakCard('6D')]) if enemy else frozenset(),
                    'slots': enemy}
            engine._count_throwins(take, {'enemy_count': enemy, 'deck_count': 0})
        self.assertFalse(engine._profile.throwin_shares)

    def test_new_game_resets_profile_and_public_memory(self):
        engine = self.small()
        engine.init('6S')
        engine._profile.record_take(0, 1, 1)
        engine._profile.record_stop(1)
        engine._profile.record_throwins(.2)
        engine._enemy.add(DurakCard('7C'))
        engine._ledger = [DurakCard('6C')]
        engine._context = {'table': engine._ledger}
        engine.init('6H')
        self.assertEqual(engine._profile.report(), OpponentProfile().report())
        self.assertEqual(engine._profile.version, 0)
        self.assertFalse(engine._enemy)
        self.assertFalse(engine._ledger)
        self.assertIsNone(engine._context)


class EngineTest(unittest.TestCase):
    def test_empty_stock_fallback_scores_match_controller_playouts(self):
        hand, enemy = ['9H', '9S', '6S', '6C'], ['TS', '8C', '7C', 'JH']
        reference = game(hand, enemy)
        for options, status in (({'max_cards': 2}, 'card_limit'),
                                ({'max_nodes': 1}, 'node_limit')):
            with self.subTest(options=options):
                # No opponent imitation: isolate the deck and rollout rules.
                engine = PuppeteerEngine(horizon=0, leaf_deck=0, explain_decisions=True, **options)
                engine.init('6S')
                data = reference.get_game_data_for(reference.PLAYER1)
                engine.deal(hand, data)
                with patch.object(engine, '_simulate', wraps=engine._simulate) as simulate:
                    engine.move([], data)
                self.assertEqual(engine.last_decision['exact_search']['status'], status)
                self.assertTrue(simulate.call_args_list)
                self.assertTrue(all(call.args[3] == [] for call in simulate.call_args_list))
                for row in engine.last_decision['candidates']:
                    controller = game(hand, enemy)
                    controller.register_move(row['cards'][0])
                    # Empty-stock cheap policy, applied through the real rules.
                    while not controller.is_game_over():
                        if controller.state == controller.States.DEALING:
                            controller.deal()
                            continue
                        attacker, defender = controller._to_move.cards, controller._to_respond.cards
                        if controller.state == controller.States.RESPONDING:
                            choices = defender.cards_that_can_beat(controller.on_table[-1])
                            controller.register_response(choices[0] if choices else None)
                        else:
                            choices = attacker.cards_that_can_be_added_to(controller.on_table)
                            if controller.state == controller.States.GIVING_MORE:
                                controller.register_give_more(choices[:len(defender) - 1])
                            else:
                                controller.register_move(choices[0] if choices else None)
                    score = (controller.winner == controller.PLAYER1) - (controller.winner == controller.PLAYER2)
                    self.assertEqual(row['score'], score, row)

    def test_complete_games_against_dummy_and_nextgen(self):
        for seed in range(4):
            for opponent in (DummyEngine(), NextGenEngine()):
                run_game(PuppeteerEngine(worlds=8, probe=8, leaf_deck=0), opponent, seed)
                run_game(opponent, PuppeteerEngine(worlds=8, probe=8, leaf_deck=0), seed)

    def test_known_opponent_cards_stay_within_the_real_hand(self):
        engine = PuppeteerEngine(worlds=4, probe=4, leaf_deck=0)
        for seed in range(6):
            run_game(engine, DummyEngine(), seed)  # play_game validates the memory

    def test_exact_endgame_and_budget_fallback(self):
        # The game's 14-card position: a cheap rollout says win, exact play says loss.
        hand = ['7C', '8S', '9S', 'TD', 'TH', 'KH']
        enemy = ['7S', 'JS', 'QH', 'KC', 'KS', 'AH', 'AS']
        live = set(map(DurakCard, hand + enemy + ['6S']))
        data = {'deck_count': 0, 'enemy_count': len(enemy),
                'discarded': list(map(str, DurakCard.all() - live))}
        for budget, strategy in ((500_000, 'exact'), (1, 'simulation')):
            engine = PuppeteerEngine(max_nodes=budget, worlds=4, probe=4,
                                     explain_decisions=True)
            engine.init('9S')
            engine.deal(hand, data)
            engine.respond(['6S'], data)
            info = engine.last_decision
            self.assertEqual(info['strategy'], strategy)
            self.assertEqual(info['exact_search']['live_cards'], 14)
            if strategy == 'exact':
                self.assertEqual(info['outcome'], -1)
            else:
                self.assertEqual(info['exact_search']['status'], 'node_limit')

    def test_explained_decisions_are_json_and_carry_the_profile(self):
        engine = RecordingEngine(worlds=48, probe=24, explain_decisions=True)
        strategies = set()
        for seed in range(2):
            run_game(engine, DummyEngine(), seed)
        for phase, table, result, info in engine.plays:
            self.assertIsNotNone(info)
            json.dumps(info)
            strategies.add(info['strategy'])
            if info['strategy'] == 'simulation':
                self.assertIn('defence_rate', info['profile'])
                self.assertTrue(info['candidates'])
        self.assertLessEqual({'forced', 'simulation'}, strategies)

    def test_decisions_are_reproducible(self):
        first = RecordingEngine(worlds=32, probe=16, leaf_deck=0)
        run_game(first, DummyEngine(), 7)
        second = RecordingEngine(worlds=32, probe=16, leaf_deck=0)
        run_game(second, DummyEngine(), 7)
        self.assertEqual(first.plays, second.plays)

    def test_taught_refusal_flows_into_attack_scores(self):
        # Our low attacks can only be beaten by the possibly hidden 9C or trump
        # 8S. Teaching that this opponent takes low plain attacks must move
        # the low-attack scores toward the take branch; trump leads (another
        # bucket) keep their evaluation.
        engine = PuppeteerEngine(worlds=64, probe=64, leaf_deck=0, explain_decisions=True)
        engine.init('6S')
        mine = ['6C', '7C', '8C', '9S', 'TS']
        hidden = ['9C', '8S', '9D', 'TD', '6S']  # 6S is the face-up bottom trump
        live = set(map(DurakCard, mine + hidden))
        data = {'deck_count': 2, 'enemy_count': 3,
                'discarded': list(map(str, DurakCard.all() - live))}

        def scores():
            engine._cards.clear()
            engine._cards.update(mine)
            engine.deal([], {'deck_count': 2, 'enemy_count': 3,
                             'discarded': data['discarded']})
            engine.move([], data)
            return {c['cards'][0]: c['score'] for c in engine.last_decision['candidates']}

        before = scores()
        trump_rate = engine._profile.trump_rate()
        for _ in range(30):
            engine._profile.record_take(0, 1.0, 1.0)
        after = scores()
        self.assertLess(engine._profile.defence_rate(0), 0.2)
        self.assertEqual(engine._profile.trump_rate(), trump_rate)
        self.assertGreater(after['6C'], before['6C'])   # they take it now: good for us
        self.assertGreater(after['7C'], before['7C'])

    def test_falls_back_to_dummy_without_game_data(self):
        engine, dummy = PuppeteerEngine(), DummyEngine()
        for player in (engine, dummy):
            player.init('6S')
            player.deal(['6C', '7C'], {})
        self.assertEqual(engine.move([], {}), str(dummy.move([], {})))
        self.assertEqual(engine._cards, dummy._cards)


if __name__ == '__main__':
    unittest.main()
