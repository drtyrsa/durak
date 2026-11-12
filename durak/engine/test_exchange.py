"""Independent matching and controller oracles for the analytic policy."""
from itertools import combinations, permutations
from random import Random
import unittest
from unittest.mock import patch

from durak.engine.hand_value import CARDS, HandAssessment, weights
from durak.engine.test_middlegame import cards, position
from durak.engine.test_nextgen import game
from durak.utils.cards import CardSet, DurakCard


class AssessmentTest(unittest.TestCase):
    def test_defensive_capacity_matches_exhaustive_assignments(self):
        rng = Random(771)
        assessment = HandAssessment(DurakCard('6S'), set(CARDS))

        def oracle(defenders, attacks):
            if not attacks:
                return 0
            attack, *rest = attacks
            return max([oracle(defenders, rest)] + [
                1 + oracle(defenders - {card}, rest)
                for card in CardSet(defenders, '6S').cards_that_can_beat(attack)])

        for _ in range(150):
            sample = rng.sample(CARDS, 10)
            defenders, attacks = set(sample[:5]), sample[5:]
            self.assertEqual(assessment.coverage(weights(defenders), weights(attacks)),
                             oracle(defenders, attacks))

    def test_one_ace_cannot_cover_several_attacks(self):
        assessment = HandAssessment(DurakCard('6S'), set(CARDS))
        self.assertEqual(assessment.coverage(weights(cards('AS')),
                                             weights(cards('6C', '6D', '6H'))), 1)
        fractional = [w / 2 for w in weights(cards('AS'))]
        self.assertEqual(assessment.coverage(fractional, weights(cards('6C', '6D'))), .5)


class ExchangeTest(unittest.TestCase):
    def test_refill_marginals_match_every_hidden_allocation_and_controller(self):
        for attacking in (False, True):
            for taken in (False, True):
                for with_gift in (False, True) if taken else (False,):
                    for known in ((), ('9D',)):
                        for full_hands in (False, True):
                            with self.subTest(attacking=attacking, taken=taken,
                                              gift=with_gift, known=known, full_hands=full_hands):
                                self.check_refills(attacking, taken, with_gift, known, full_hands)

    def check_refills(self, attacking, taken, with_gift, known, full_hands):
        hand = cards('6H', '7H', 'AS')
        table = tuple(map(DurakCard, ('6C',) if taken else ('6C', '7C')))
        enemy, deck = cards('6D', '9D'), cards('QC', 'KD', '6S')
        if full_hands:
            hand |= cards('8C', '8D', '8H')
            enemy |= cards('TH', 'JH', 'QH')
        given = cards('6H' if attacking else '6D') if with_gift else set()
        policy, _ = position(hand, enemy, deck, table, known=known)
        evaluator = policy._evaluator
        with patch.object(evaluator.assessment, 'evaluate',
                          wraps=evaluator.assessment.evaluate) as assess:
            result = evaluator.settle(frozenset(hand), table, len(enemy),
                                      frozenset(map(DurakCard, known)), attacking, taken, given)
        own_weights, enemy_weights, remaining, initiative = assess.call_args.args
        own_total, enemy_total = [0.0] * 36, [0.0] * 36
        samples = 0
        pool = sorted((enemy | deck) - cards('6S'))
        arrangements = ((set(opposing), order) for opposing in combinations(pool, len(enemy))
                        for order in permutations(sorted(set(pool) - set(opposing))))
        for opposing, order in arrangements:
            if not set(map(DurakCard, known)) <= opposing:
                continue
            if taken and not attacking and not given <= opposing:
                continue
            controller = game(hand, opposing, table=table)
            controller._deck = list(order) + [DurakCard('6S')]
            controller._discarded = list(set(controller._discarded) - set(controller._deck))
            controller._to_move = controller._player1 if attacking else controller._player2
            controller._no_response = taken
            controller._on_table.give_more(given)
            controller._to_move.cards.difference_update(given)
            controller._state = controller.States.DEALING
            controller.deal()
            for totals, actual in ((own_total, controller._player1.cards),
                                   (enemy_total, controller._player2.cards)):
                for i, weight in enumerate(weights(actual)):
                    totals[i] += weight
            samples += 1
            self.assertEqual(remaining, controller.deck_count)
            self.assertEqual(initiative, 1 if controller.is_player1_to_move() else -1)
            recipient = (None if controller.deck_count else
                         'ours' if DurakCard('6S') in controller._player1.cards else 'enemy')
            self.assertEqual(result['draws']['face_up_to'], recipient)
        self.assertGreater(samples, 0)
        for expected, totals in ((own_weights, own_total), (enemy_weights, enemy_total)):
            for marginal, total in zip(expected, totals):
                self.assertAlmostEqual(marginal, total / samples)

    def test_best_available_reply_probabilities_match_hidden_hands(self):
        policy, _ = position(['6C'], ['7C', '8C'], ['9C', 'TC', '6S'], known=['7C'])
        evaluator = policy._evaluator
        alternatives = [(DurakCard(c), v) for c, v in [('7C', 2), ('8C', -3), ('9C', -1), ('TC', 7)]]
        values = []
        for rest in combinations(sorted(policy.unknown), policy.unknown_count):
            enemy = set(rest) | policy.known_enemy
            values.append(min([4] + [v for c, v in alternatives if c in enemy]))
        actual = evaluator.enemy_choice(4, alternatives, frozenset(policy.hand), (),
                                        policy.enemy_count, frozenset(policy.known_enemy))
        self.assertAlmostEqual(actual, sum(values) / len(values))

    def test_fully_remembered_hand_excludes_unknown_stock_from_replies(self):
        policy, _ = position(['7H', '8H', 'AS'], ['7C', '9C'], ['6S', 'KC', 'AC'],
                             table=['6H'], known=['7C', '9C'])
        pool, certain, slots = policy._evaluator.belief(
            frozenset(policy.hand), policy.table, 2, frozenset(policy.known_enemy))
        self.assertFalse(pool)
        self.assertEqual(certain, cards('7C', '9C'))
        self.assertEqual(slots, 0)
        self.assertIn(policy.respond(), ((DurakCard('7H'),), (DurakCard('8H'),),
                                        (DurakCard('AS'),), ()))

    def test_pickup_accounts_for_joint_throw_ins_and_capacity(self):
        def exchange(hand, table, count, known, attacking, taken, given=()):
            # Two matching cards together can be much worse than either alone.
            return {'score': -8 if len(given) == 2 else -2 if DurakCard('6H') in given
                    else -1 if given else 0}

        for hand, expected in [(['8C', '9C', 'TC'], -4.5), (['8C', '9C'], -1.5), (['8C'], 0)]:
            policy, _ = position(hand, ['6D', '6H'], ['7H', '6S'], table=['6C'], known=['6D'])
            evaluator = policy._evaluator
            with patch.object(evaluator, 'settle', side_effect=exchange):
                self.assertAlmostEqual(evaluator.take(frozenset(policy.hand), policy.table, 2,
                                                       frozenset(policy.known_enemy)), expected)


if __name__ == '__main__':
    unittest.main()
