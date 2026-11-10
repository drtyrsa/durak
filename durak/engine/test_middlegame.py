"""Public-information boundaries and complete controller-backed games."""
from itertools import combinations
import json
import subprocess
import sys
import unittest

from durak.engine.dummy import DummyEngine
from durak.engine.matchup import DealRandom, play_game
from durak.engine.middlegame import CardMemory, MiddlegamePolicy
from durak.engine.nextgen import NextGenEngine
from durak.utils.cards import CardSet, DurakCard


def cards(*values):
    return set(map(DurakCard, values))


def position(hand, enemy, deck, table=(), trump='6S', known=()):
    """Build public metadata; the policy never receives the enemy/deck split."""
    hand = CardSet(hand, trump)
    table = tuple(map(DurakCard, table))
    live = hand | set(map(DurakCard, enemy)) | set(map(DurakCard, deck)) | set(table)
    data = {'deck_count': len(deck), 'enemy_count': len(enemy),
            'discarded': list(map(str, sorted(DurakCard.all() - live)))}
    return MiddlegamePolicy(hand, DurakCard(trump), table, data, map(DurakCard, known)), data


class PublicInformationTest(unittest.TestCase):
    def test_probabilities_match_enumerated_hidden_hands(self):
        policy, _ = position(['6C'], ['7C', '8C', '9C'], ['TC', 'JC', '6S'], known=['7C'])
        assignments = [policy.known_enemy | set(rest)
                       for rest in combinations(sorted(policy.unknown), policy.unknown_count)]
        for target in (cards('7C'), cards('8C'), cards('8C', 'TC'), cards('6S'), set()):
            expected = sum(bool(hand & target) for hand in assignments) / len(assignments)
            self.assertAlmostEqual(policy.probability_has(target), expected)
        self.assertNotIn(DurakCard('6S'), policy.possible_enemy)

    def test_hidden_allocation_cannot_change_decision(self):
        first, _ = position(['6C', '7H', '8H'], ['9C', '9H'], ['TC', 'TH', '6S'])
        second, _ = position(['6C', '7H', '8H'], ['TC', 'TH'], ['9C', '9H', '6S'])
        self.assertEqual(first.move(), second.move())
        self.assertEqual(first.possible_enemy, second.possible_enemy)

    def test_discarded_suit_and_rank_cannot_be_in_opponents_hand(self):
        policy, _ = position(['6C', '7C'], ['8C', '9D'], ['TC', '6S'])
        # Every heart and every queen is in the public discard pile.
        for target in ({c for c in DurakCard.all() if c.suit == 'H'},
                       {c for c in DurakCard.all() if c.rank == 'Q'}):
            self.assertEqual(policy.probability_has(target), 0.0)

    def test_last_face_up_card_makes_enemy_hand_certain_before_deck_is_empty(self):
        policy, _ = position(['6C', '7C'], ['8C', '9D', 'AS'], ['6S'])
        for card in cards('8C', '9D', 'AS'):
            self.assertEqual(policy.probability_has({card}), 1.0)
        self.assertEqual(policy.probability_has(cards('6S')), 0.0)

    def test_probability_increases_as_unknown_draw_cards_disappear(self):
        early, _ = position(['6C'], ['7C', '8C'], ['9C', 'TC', 'JC', '6S'])
        late, _ = position(['6C'], ['7C', '8C'], ['9C', '6S'])
        self.assertAlmostEqual(early.probability_has(cards('7C')), 2 / 5)
        self.assertAlmostEqual(late.probability_has(cards('7C')), 2 / 3)

    def test_remember_pickup_and_throw_ins_then_forget_played_cards(self):
        memory = CardMemory()
        memory.observe('give_more', cards('6C', '7C', '7D'), cards('6D', 'AS'), set())
        memory.played(cards('6D'))
        memory.deal(cards('AS', '9S'), {'discarded': []})
        self.assertEqual(memory.enemy, cards('6C', '7C', '7D', '6D'))
        memory.observe('respond', cards('7C'), cards('AS', '9S'), set())
        self.assertEqual(memory.enemy, cards('6C', '7D', '6D'))

    def test_defence_discards_and_own_pickups_are_not_enemy_cards(self):
        memory = CardMemory()
        memory.observe('move', cards('6C', '7C'), cards('AS'), set())
        memory.deal(cards('AS'), {'discarded': ['6C', '7C']})
        self.assertFalse(memory.enemy)
        memory.observe('respond', cards('8C'), cards('AS'), cards('6C', '7C'))
        memory.deal(cards('AS', '8C'), {'discarded': ['6C', '7C']})
        self.assertFalse(memory.enemy)

    def test_last_attack_pickup_without_give_more_callback(self):
        memory = CardMemory()
        memory.observe('move', (), cards('6C'), set())
        memory.played(cards('6C'))
        memory.deal(cards('AS'), {'discarded': []})
        self.assertEqual(memory.enemy, cards('6C'))

    def test_missing_bout_result_drops_uncertain_memory_and_init_resets(self):
        engine = NextGenEngine()
        engine.init('6S')
        engine._memory.enemy = cards('7C')
        engine.deal(['6C'], {})
        self.assertFalse(engine._memory.enemy)
        engine._memory.enemy = cards('7C')
        engine.init('6H')
        self.assertFalse(engine._memory.enemy)
        self.assertFalse(engine._memory.table)

    def test_inconsistent_metadata_is_not_used_for_probabilities(self):
        policy, data = position(['6C'], ['7C'], ['8C', '6S'])
        self.assertTrue(MiddlegamePolicy.available(policy.hand, policy.trump, (), data))
        for bad in ({}, {**data, 'enemy_count': 20}, {**data, 'deck_count': -1},
                    {**data, 'discarded': data['discarded'] + ['6C']}):
            self.assertFalse(MiddlegamePolicy.available(policy.hand, policy.trump, (), bad))


class MiddlegameIntegrationTest(unittest.TestCase):
    def test_ace_trump_diagnostic_admits_taking_was_not_evaluated(self):
        hand = ['6D', '8D', 'TH', 'KH', 'AD', 'AS']
        _, data = position(hand, ['7C', '9C', 'JC', 'QC', 'AC'],
                           ['7D', '9H', 'JH', 'QS', 'KS', '6S'], table=['6C'])
        outputs = []
        for explain in (False, True):
            engine = NextGenEngine(explain_decisions=explain)
            engine.init('6S')
            engine.deal(hand, data)
            outputs.append(str(engine.respond(['6C'], data)))
        self.assertEqual(outputs, ['AS', 'AS'])
        record = engine.last_decision
        self.assertEqual(record['strategy'], 'smart')
        self.assertEqual(record['gamedata']['deck_count'], 6)
        self.assertIn('AS', record['hand'])  # position before the move, not afterwards
        take = next(c for c in record['candidates'] if c['action'] == 'take')
        self.assertFalse(take['evaluated'])
        self.assertFalse(take['selected'])
        self.assertIsNone(take['score'])
        self.assertEqual(record['belief']['card_probabilities']['6S'], 0)
        self.assertIsNone(engine.last_solution)

    def test_matching_rank_attack_is_preferred_to_isolated_lowest_card(self):
        hand = ['6C', '8C', '7D', '7H', 'QS', 'AS']
        unseen = sorted(DurakCard.all() - set(map(DurakCard, hand)) - cards('6S'))
        _, data = position(hand, unseen[:6], unseen[6:] + [DurakCard('6S')])
        outputs = []
        for strategy in ('smart', 'dummy'):
            engine = NextGenEngine(middlegame=strategy)
            engine.init('6S')
            engine.deal(hand, data)
            outputs.append(str(engine.move([], data)))
        self.assertEqual(outputs, ['7D', '6C'])

    def test_defence_avoids_exposing_a_known_enemy_rank(self):
        policy, _ = position(['7H', '8H', '9D', 'QS'], ['7C', '9C'],
                             ['6S', 'KC', 'AC'], table=['6H'], known=['7C'])
        self.assertEqual(policy.respond(), (DurakCard('8H'),))

    def test_keeps_cover_for_another_suit(self):
        hand = ['8C', '8D', 'KC']
        unseen = sorted(DurakCard.all() - set(map(DurakCard, hand)) - cards('6S'))
        policy, _ = position(hand, unseen[:6], unseen[6:] + [DurakCard('6S')])
        self.assertEqual(policy.move(), (DurakCard('8C'),))

    def test_spends_a_cheap_trump_to_defend(self):
        policy, _ = position(['7S', 'AS', '9C'], ['7C', '9D'],
                             ['6S', 'AC'], table=['KC'])
        self.assertEqual(policy.respond(), (DurakCard('7S'),))

    def test_throw_ins_respect_capacity_and_preserve_trumps(self):
        policy, _ = position(['7S', '7C', '6D'], ['9C', '9D'],
                             ['6S', 'AC'], table=['6C', '7D', '6H'])
        self.assertEqual(policy.give_more(), (DurakCard('6D'),))
        policy.enemy_count = 1
        self.assertEqual(policy.give_more(), ())

    def test_complete_games_with_public_memory_and_legal_moves(self):
        for seed in range(20):
            other = (DummyEngine() if seed % 3 == 0 else NextGenEngine(
                middlegame='dummy' if seed % 3 == 1 else 'smart'))
            play_game(NextGenEngine(), other, seed)

    def test_deal_seed_does_not_depend_on_set_iteration_order(self):
        first = sorted(DurakCard.all())
        second = list(reversed(first))
        DealRandom(123).shuffle(first)
        DealRandom(123).shuffle(second)
        self.assertEqual(first, second)

    def test_strategy_switch_keeps_protocol_stdout_clean(self):
        _, data = position(['6C', '7H', '8H'], ['9C', '9H'], ['TC', 'TH', '6S'])
        commands = 'init 6S\ndeal 6C 7H 8H\nmove ## ' + json.dumps(data) + '\ngame_end\n'
        for strategy in ('smart', 'dummy'):
            result = subprocess.run([sys.executable, '-m', 'durak.engine.nextgen',
                                     '--middlegame', strategy], input=commands,
                                    capture_output=True, text=True, check=True, timeout=10)
            self.assertEqual(result.stdout.splitlines()[:2], ['ok', 'ok'])
            self.assertIn(result.stdout.splitlines()[2], ('6C', '7H', '8H'))
            self.assertEqual(result.stderr, '')

    def test_unknown_strategy_rejected(self):
        with self.assertRaises(ValueError):
            NextGenEngine(middlegame='random')
