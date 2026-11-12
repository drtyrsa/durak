"""Smart Runner: simulator fidelity against GameController, tracking, engine play."""
from random import Random
import json
import unittest
from unittest.mock import patch

from durak.controller import GameController, Table
from durak.engine.dummy import DummyEngine
from durak.engine.matchup import DealRandom, play_game
from durak.engine.nextgen import NextGenEngine
from durak.engine.simulator import GIVE, MOVE, RESPOND, Universe, rollout
from durak.engine.smart_runner import SmartRunnerEngine
from durak.utils.cards import CardSet, DurakCard

PHASES = {'moving': 'move', 'responding': 'respond', 'giving_more': 'give_more'}


def value(card, trump):
    return (card.suit == trump.suit, card.numeric_rank, DurakCard.SUITS.index(card.suit))


def policy(controller):
    """The simulator's rollout policy, written against the controller API."""
    trump = controller._trump
    phase = PHASES[controller.state]
    attacker, defender = controller._to_move.cards, controller._to_respond.cards
    table = controller.on_table
    if phase == 'respond':
        options = [c for c in defender if c in defender.cards_that_can_beat(table[-1])]
        return (min(options, key=lambda c: value(c, trump)),) if options else ()
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


def simulate(controller, action):
    """Winner seat (0 = player1) from the bit-mask simulator."""
    u = Universe(controller._trump)
    phase = PHASES[controller.state]
    attacker = 0 if controller.is_player1_to_move() else 1
    table = controller.on_table
    pending = u.bit[table[-1]] if phase == 'respond' else 0
    hands = [u.mask(controller._player1.cards), u.mask(controller._player2.cards)]
    deck = [u.bit[c] for c in reversed(controller._deck)]
    mode = {'move': MOVE, 'respond': RESPOND, 'give_more': GIVE}[phase]
    result = rollout(u, hands, deck, attacker, u.mask(table), pending, mode, u.mask(action))
    return {0: 'player1', 1: 'player2', -1: None}[result]


class SimulatorTest(unittest.TestCase):
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
            for action in legal(controller):
                reference = clone(controller)
                apply(reference, action)
                while not reference.is_game_over():
                    apply(reference, policy(reference))
                endings.add(reference.winner)
                self.assertEqual(simulate(controller, action), reference.winner, (seed, action))
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

        def sample(u, hands, *args, **kwargs):
            sampled_hands.append(u.unpack(hands[1]))
            return -1  # equal outcomes: no throw-ins, independent of rollout policy

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

    def test_falls_back_to_dummy_without_game_data(self):
        engine, dummy = SmartRunnerEngine(), DummyEngine()
        for player in (engine, dummy):
            player.init('6S')
            player.deal(['6C', '7C'], {})
        self.assertEqual(engine.move([], {}), str(dummy.move([], {})))
        self.assertEqual(engine._cards, dummy._cards)


if __name__ == '__main__':
    unittest.main()
