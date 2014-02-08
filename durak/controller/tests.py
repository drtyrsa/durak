# -*- coding: utf-8 -*-
import unittest

from mock import patch

from durak.utils.cards import DurakCard, CardSet
from durak.controller import Table, GameController
import durak.controller.exceptions as exes


class TableTest(unittest.TestCase):

    def test_initial_given_more(self):
        table = Table()
        self.assertTrue(isinstance(table, list))
        self.assertEqual(table.given_more, set())

    def test_give_more_updates_given_more(self):
        table = Table()
        self.assertEqual(table.given_more, set())

        cards = {DurakCard('AH'), DurakCard('6H')}
        table.give_more(cards)

        self.assertEqual(table.given_more, cards)

    def test_clear(self):
        table = Table()
        cards = {DurakCard('AH'), DurakCard('6H')}
        given_more_cards = {DurakCard('AS'), DurakCard('6S')}

        table.extend(cards)
        self.assertItemsEqual(table, cards)
        table.give_more(given_more_cards)
        self.assertEqual(table.given_more, given_more_cards)

        table.clear()

        self.assertEqual(table, [])
        self.assertEqual(table.given_more, set())


class GameControllerTest(unittest.TestCase):

    def test_get_first_to_move_by_trump_if_both_trumps_exist(self):
        controller = GameController()
        controller._trump = DurakCard('6H')
        controller._player1.cards = CardSet(
            cards=(DurakCard('7H'), DurakCard('8S')), trump=controller._trump
        )
        controller._player2.cards = CardSet(
            cards=(DurakCard('9H'), DurakCard('KD')), trump=controller._trump
        )
        self.assertEqual(
            controller._get_first_to_move_by_trump(), controller._player1
        )

        controller._player1.cards = CardSet(
            cards=(DurakCard('AH'), DurakCard('8S')), trump=controller._trump
        )
        self.assertEqual(
            controller._get_first_to_move_by_trump(), controller._player2
        )

    def test_get_first_to_move_by_trump_if_only_one_trump_exists(self):
        controller = GameController()
        controller._trump = DurakCard('6H')
        controller._player1.cards = CardSet(
            cards=(DurakCard('7H'), DurakCard('8S')), trump=controller._trump
        )
        controller._player2.cards = CardSet(
            cards=(DurakCard('KS'), DurakCard('KD')), trump=controller._trump
        )
        self.assertEqual(
            controller._get_first_to_move_by_trump(), controller._player1
        )

        controller._player1.cards = CardSet(
            cards=(DurakCard('AC'), DurakCard('8S')), trump=controller._trump
        )
        controller._player2.cards = CardSet(
            cards=(DurakCard('9H'), DurakCard('KD')), trump=controller._trump
        )
        self.assertEqual(
            controller._get_first_to_move_by_trump(), controller._player2
        )

    def test_get_first_to_move_by_trump_if_only_no_trumps_exist(self):
        controller = GameController()
        controller._trump = DurakCard('6H')
        controller._player1.cards = CardSet(
            cards=(DurakCard('AC'), DurakCard('8S')), trump=controller._trump
        )
        controller._player2.cards = CardSet(
            cards=(DurakCard('KS'), DurakCard('KD')), trump=controller._trump
        )
        with patch('durak.controller.random') as random_mock:
            result = controller._get_first_to_move_by_trump()
            self.assertEqual(result, random_mock.choice.return_value)
            random_mock.choice.assert_called_once_with(
                [controller._player1, controller._player2]
            )

    def test_state(self):
        controller = GameController()
        states = {
            controller.States.MOVING,
            controller.States.RESPONDING,
            controller.States.GIVING_MORE,
            controller.States.DEALING
        }
        for state in states:
            controller._state = state
            self.assertEqual(controller.state, state)

    def test_is_player1_to_move(self):
        controller = GameController()
        controller._to_move = controller._player1
        self.assertTrue(controller.is_player1_to_move())

        controller._to_move = controller._player2
        self.assertFalse(controller.is_player1_to_move())

    def test_get_enemy_of(self):
        controller = GameController()
        self.assertEqual(
            controller._get_enemy_of(controller._player1), controller._player2
        )
        self.assertEqual(
            controller._get_enemy_of(controller._player2), controller._player1
        )

    def test_to_respond(self):
        controller = GameController()
        controller._to_move = controller._player1
        self.assertEqual(controller._to_respond, controller._player2)

        controller._to_move = controller._player2
        self.assertEqual(controller._to_respond, controller._player1)

    def test_game_data_for_private(self):
        controller = GameController()
        controller._trump = DurakCard('6H')
        controller._deck = [DurakCard('7S'), DurakCard('8D')]
        controller._on_table = [DurakCard('9C'), DurakCard('TH')]
        controller._discarded = [DurakCard('JD'), DurakCard('QS')]
        controller._player1.cards = CardSet(
            cards=(DurakCard('AC'), DurakCard('8S'), DurakCard('KS')),
            trump=controller._trump
        )
        controller._player2.cards = CardSet(
            cards=(DurakCard('KD'),), trump=controller._trump
        )
        self.assertDictEqual(
            controller._get_game_data_for(controller._player1), {
                'trump': str(controller._trump),
                'deck_count': len(controller._deck),
                'enemy_count': len(controller._player2.cards),
                'on_table': map(str, controller._on_table),
                'discarded': map(str, controller._discarded),
            }
        )
        self.assertDictEqual(
            controller._get_game_data_for(controller._player2), {
                'trump': str(controller._trump),
                'deck_count': len(controller._deck),
                'enemy_count': len(controller._player1.cards),
                'on_table': map(str, controller._on_table),
                'discarded': map(str, controller._discarded),
            }
        )

    def test_game_data_for_public(self):
        controller = GameController()
        controller._trump = DurakCard('6H')
        controller._deck = [DurakCard('7S'), DurakCard('8D')]
        controller._on_table = [DurakCard('9C'), DurakCard('TH')]
        controller._discarded = [DurakCard('JD'), DurakCard('QS')]
        controller._player1.cards = CardSet(
            cards=(DurakCard('AC'), DurakCard('8S'), DurakCard('KS')),
            trump=controller._trump
        )
        controller._player2.cards = CardSet(
            cards=(DurakCard('KD'),), trump=controller._trump
        )
        controller._to_move = controller._player1
        self.assertDictEqual(
            controller.get_game_data_for(controller.PLAYER1),
            controller._get_game_data_for(controller._player1)
        )
        self.assertDictEqual(
            controller.get_game_data_for(controller.PLAYER2),
            controller._get_game_data_for(controller._player2)
        )
        self.assertDictEqual(
            controller.get_game_data_for(controller.MOVER),
            controller._get_game_data_for(controller._player1)
        )
        self.assertDictEqual(
            controller.get_game_data_for(controller.RESPONDER),
            controller._get_game_data_for(controller._player2)
        )

    def test_start_new_game_players_and_deck_cards(self):
        controller = GameController()
        controller.start_new_game()
        self.assertEqual(controller._trump, controller._deck[-1])

        all_cards = []
        all_cards.extend(controller._deck)
        all_cards.extend(controller._player1.cards)
        all_cards.extend(controller._player2.cards)
        self.assertItemsEqual(all_cards, DurakCard.all())

    def test_start_new_game_cards_are_shuffled(self):
        controller = GameController()
        with patch('durak.controller.random') as random_mock:
            controller.start_new_game()
            random_mock.shuffle.assert_called_once_with(list(DurakCard.all()))

    def test_if_winner_is_none_first_move_is_selected_by_trump(self):
        controller = GameController()
        self.assertTrue(controller._winner is None)

        with patch.object(controller,
                          '_get_first_to_move_by_trump') as _get_first_mock:
            controller.start_new_game()
            self.assertEqual(controller._to_move, _get_first_mock.return_value)

    def test_if_winner_is_ignored_first_move_is_selected_by_trump(self):
        controller = GameController()
        controller._winner = controller._player1

        with patch.object(controller,
                          '_get_first_to_move_by_trump') as _get_first_mock:
            controller.start_new_game()
            self.assertEqual(controller._to_move, _get_first_mock.return_value)

    def test_if_winner_and_not_ignored_it_selects_first_move(self):
        controller = GameController()
        controller._winner = controller._player1

        with patch.object(controller,
                          '_get_first_to_move_by_trump') as _get_first_mock:
            controller.start_new_game(ignore_winner=False)
            self.assertEqual(controller._to_move, controller._player1)
            self.assertFalse(_get_first_mock.called)

    def test_start_new_game_return_value_and_state(self):
        controller = GameController()
        result = controller.start_new_game()
        self.assertDictEqual(result, {
            'player1_cards': set(controller._player1.cards),
            'player2_cards': set(controller._player2.cards),
            'trump': controller._trump,
        })
        self.assertEqual(controller.state, controller.States.MOVING)

    def test_is_game_over_is_true_if_state_is_none(self):
        controller = GameController()
        controller._state = None
        self.assertTrue(controller.is_game_over())

    def test_is_game_over_is_false_if_state_is_not_none(self):
        controller = GameController()
        controller._state = controller.States.MOVING
        self.assertFalse(controller.is_game_over())

    def test_check_for_game_over_does_nothing_if_deck_is_not_empty(self):
        controller = GameController()
        controller._state = controller.States.MOVING
        controller._deck = [DurakCard('7S'), DurakCard('8D')]
        controller._check_for_game_over()
        self.assertEqual(controller._state, controller.States.MOVING)

    def test_check_for_game_over_does_nothing_if_both_players_have_cards(self):
        controller = GameController()
        controller._trump = DurakCard('6H')
        controller._deck = []
        controller._player1.cards = CardSet(
            cards=(DurakCard('AC'), DurakCard('8S')), trump=controller._trump
        )
        controller._player2.cards = CardSet(
            cards=(DurakCard('KD'), DurakCard('KS')), trump=controller._trump
        )
        controller._state = controller.States.MOVING
        controller._check_for_game_over()
        self.assertEqual(controller._state, controller.States.MOVING)

    def test_check_for_game_over_does_nothing_if_responder_can_beat_with_last_card(self):
        controller = GameController()
        controller._state = controller.States.RESPONDING
        controller._deck = []
        controller._trump = DurakCard('6H')
        controller._player1.cards = CardSet(cards=(), trump=controller._trump)
        controller._player2.cards = CardSet(
            cards=(DurakCard('KD'),), trump=controller._trump
        )
        controller._to_move = controller._player1
        controller._on_table = [DurakCard('QD')]
        controller._check_for_game_over()
        self.assertEqual(controller._state, controller.States.RESPONDING)

    def test_check_for_game_over_is_draw_if_both_players_have_no_cards(self):
        controller = GameController()
        controller._trump = DurakCard('6H')
        controller._deck = []
        controller._player1.cards = CardSet(cards=(), trump=controller._trump)
        controller._player2.cards = CardSet(cards=(), trump=controller._trump)
        controller._state = controller.States.MOVING

        controller._check_for_game_over()
        self.assertTrue(controller._state is None)
        self.assertTrue(controller._winner is None)

    def test_check_for_game_over_player_wins_if_has_no_cards(self):
        controller = GameController()
        controller._trump = DurakCard('6H')
        controller._deck = []
        controller._player1.cards = CardSet(cards=(), trump=controller._trump)
        controller._player2.cards = CardSet(
            cards=(DurakCard('KD'), DurakCard('KS')), trump=controller._trump
        )
        controller._state = controller.States.MOVING
        controller._check_for_game_over()
        self.assertTrue(controller._state is None)
        self.assertEqual(controller._winner, controller._player1)

        controller._player1.cards = CardSet(
            cards=(DurakCard('AC'), DurakCard('8S')), trump=controller._trump
        )
        controller._player2.cards = CardSet(cards=(), trump=controller._trump)
        controller._state = controller.States.MOVING
        controller._check_for_game_over()
        self.assertTrue(controller._state is None)
        self.assertEqual(controller._winner, controller._player2)

    def test_register_move_is_error_if_state_is_not_moving(self):
        controller = GameController()
        controller._state = controller.States.RESPONDING
        with self.assertRaises(exes.InvalidAction):
            controller.register_move(DurakCard('AC'))

    def test_register_move_card_can_not_be_none_on_empty_table(self):
        controller = GameController()
        controller._state = controller.States.MOVING
        controller._on_table = []
        with self.assertRaises(exes.CardIsExpected):
            controller.register_move(None)

    def test_register_move_goes_to_responding_if_card_is_none(self):
        controller = GameController()
        controller._state = controller.States.MOVING
        controller._on_table = [DurakCard('AC'), DurakCard('AH')]

        controller.register_move(None)

        self.assertEqual(controller._state, controller.States.DEALING)

    def test_register_move_is_error_if_player_does_have_this_card(self):
        controller = GameController()
        controller._state = controller.States.MOVING
        controller._to_move = controller._player1
        controller._trump = DurakCard('6H')
        controller._player1.cards = CardSet(
            cards=(DurakCard('AC'), DurakCard('AH')), trump=controller._trump
        )
        controller._on_table = []

        with self.assertRaises(exes.PlayerDoesNotHaveCard):
            controller.register_move(DurakCard('6D'))

    def test_register_move_is_error_if_player_can_not_add_this_card(self):
        controller = GameController()
        controller._state = controller.States.MOVING
        controller._to_move = controller._player1
        controller._trump = DurakCard('6H')
        controller._player1.cards = CardSet(
            cards=(DurakCard('AC'), DurakCard('AH')), trump=controller._trump
        )
        controller._on_table = [DurakCard('6H'), DurakCard('7D')]

        with self.assertRaises(exes.InvalidCard):
            controller.register_move(DurakCard('AC'))

    def test_successful_register_move(self):
        controller = GameController()
        controller._state = controller.States.MOVING
        controller._to_move = controller._player1
        controller._trump = DurakCard('6H')
        controller._deck = [DurakCard('6H')]
        controller._player1.cards = CardSet(
            cards=(DurakCard('AC'), DurakCard('7H')), trump=controller._trump
        )
        controller._on_table = [DurakCard('AD'), DurakCard('AS')]

        controller.register_move(DurakCard('AC'))

        self.assertItemsEqual(controller._player1.cards, (DurakCard('7H'),))
        self.assertEqual(
            controller._on_table,
            [DurakCard('AD'), DurakCard('AS'), DurakCard('AC')]
        )
        self.assertEqual(controller._state, controller.States.RESPONDING)

    def test_register_response_is_error_if_state_is_not_responding(self):
        controller = GameController()
        controller._state = controller.States.MOVING
        with self.assertRaises(exes.InvalidAction):
            controller.register_response(DurakCard('AC'))

    def test_register_response_goes_to_giving_more_if_card_is_none(self):
        controller = GameController()
        controller._state = controller.States.RESPONDING
        controller._to_move = controller._player1
        controller._trump = DurakCard('6H')
        controller._player1.cards = CardSet(
            cards=(DurakCard('AC'),), trump=controller._trump
        )

        controller.register_response(None)

        self.assertEqual(controller._state, controller.States.GIVING_MORE)
        self.assertTrue(controller._no_response)

    def test_register_response_goes_to_dealing_if_card_is_none_and_mover_has_no_cards(self):
        controller = GameController()
        controller._state = controller.States.RESPONDING
        controller._to_move = controller._player1
        controller._trump = DurakCard('6H')
        controller._player1.cards = CardSet(cards=(), trump=controller._trump)

        controller.register_response(None)

        self.assertEqual(controller._state, controller.States.DEALING)
        self.assertTrue(controller._no_response)

    def test_register_response_is_error_if_player_does_have_this_card(self):
        controller = GameController()
        controller._state = controller.States.RESPONDING
        controller._to_move = controller._player2
        controller._trump = DurakCard('6H')
        controller._player1.cards = CardSet(
            cards=(DurakCard('AC'), DurakCard('AH')), trump=controller._trump
        )
        controller._on_table = [DurakCard('6D')]

        with self.assertRaises(exes.PlayerDoesNotHaveCard):
            controller.register_response(DurakCard('7D'))

    def test_register_response_is_error_if_player_can_not_add_this_card(self):
        controller = GameController()
        controller._state = controller.States.RESPONDING
        controller._to_move = controller._player2
        controller._trump = DurakCard('6H')
        controller._player1.cards = CardSet(
            cards=(DurakCard('AC'), DurakCard('AH')), trump=controller._trump
        )
        controller._on_table = [DurakCard('6D')]

        with self.assertRaises(exes.InvalidCard):
            controller.register_response(DurakCard('AC'))

    def test_register_response_moves_card_from_player_to_table(self):
        controller = GameController()
        controller._state = controller.States.RESPONDING
        controller._to_move = controller._player2
        controller._trump = DurakCard('6H')
        controller._deck = [DurakCard('JH')]
        controller._player1.cards = CardSet(
            cards=(DurakCard('AC'), DurakCard('AH')), trump=controller._trump
        )
        controller._on_table = [DurakCard('6D')]

        controller.register_response(DurakCard('AH'))

        self.assertItemsEqual(controller._player1.cards, [DurakCard('AC')])
        self.assertEqual(
            controller._on_table, [DurakCard('6D'), DurakCard('AH')]
        )

    def test_register_response_allows_moving_if_it_is_ok(self):
        controller = GameController()
        controller._state = controller.States.RESPONDING
        controller._to_move = controller._player2
        controller._first_discard_completed = True
        controller._trump = DurakCard('6H')
        controller._deck = [DurakCard('JH')]
        controller._player1.cards = CardSet(
            cards=(DurakCard('AC'), DurakCard('AH')), trump=controller._trump
        )
        controller._player2.cards = CardSet(
            cards=(DurakCard('KC'),), trump=controller._trump
        )
        controller._on_table = [DurakCard('6D')]

        controller.register_response(DurakCard('AH'))

        self.assertEqual(controller.state, controller.States.MOVING)

    def test_register_response_not_allows_moving_if_moving_has_no_cards(self):
        controller = GameController()
        controller._state = controller.States.RESPONDING
        controller._to_move = controller._player2
        controller._trump = DurakCard('6H')
        controller._deck = [DurakCard('JH')]
        controller._player1.cards = CardSet(
            cards=(DurakCard('AC'), DurakCard('AH')), trump=controller._trump
        )
        controller._player2.cards = CardSet(cards=(), trump=controller._trump)
        controller._on_table = [DurakCard('6D')]

        controller.register_response(DurakCard('AH'))

        self.assertEqual(controller.state, controller.States.DEALING)

    def test_register_response_not_allows_moving_if_responding_has_no_cards(self):
        controller = GameController()
        controller._state = controller.States.RESPONDING
        controller._to_move = controller._player2
        controller._trump = DurakCard('6H')
        controller._deck = [DurakCard('JH')]
        controller._player1.cards = CardSet(
            cards=(DurakCard('AH'),), trump=controller._trump
        )
        controller._player2.cards = CardSet(
            cards=(DurakCard('AC'),), trump=controller._trump
        )
        controller._on_table = [DurakCard('6D')]

        controller.register_response(DurakCard('AH'))

        self.assertEqual(controller.state, controller.States.DEALING)

    def test_register_response_not_allows_moving_if_first_discard(self):
        controller = GameController()
        controller._state = controller.States.RESPONDING
        controller._first_discard_completed = False
        controller._to_move = controller._player2
        controller._trump = DurakCard('6H')
        controller._deck = [DurakCard('JH')]
        controller._player1.cards = CardSet(
            cards=(DurakCard('AH'), DurakCard('KC')), trump=controller._trump
        )
        controller._player2.cards = CardSet(
            cards=(DurakCard('AC'),), trump=controller._trump
        )
        controller._on_table = [
            DurakCard('7D'),
            DurakCard('8D'),
            DurakCard('7C'),
            DurakCard('8C'),
            DurakCard('7H'),
            DurakCard('8H'),
            DurakCard('7S'),
            DurakCard('8S'),
            DurakCard('6D')
        ]

        controller.register_response(DurakCard('AH'))

        self.assertEqual(controller.state, controller.States.DEALING)

    def test_register_give_more_is_error_if_state_is_not_giving_more(self):
        controller = GameController()
        controller._state = controller.States.MOVING
        controller._no_response = True
        with self.assertRaises(exes.InvalidAction):
            controller.register_give_more([DurakCard('AC')])

    def test_register_give_more_with_no_cards_goes_to_dealing(self):
        controller = GameController()
        controller._state = controller.States.GIVING_MORE
        controller._no_response = True

        controller.register_give_more([])

        self.assertEqual(controller.state, controller.States.DEALING)

    def test_register_give_more_is_error_if_player_does_have_these_cards(self):
        controller = GameController()
        controller._state = controller.States.GIVING_MORE
        controller._no_response = True
        controller._to_move = controller._player1
        controller._trump = DurakCard('6H')
        controller._player1.cards = CardSet(
            cards=(DurakCard('AC'), DurakCard('AH')), trump=controller._trump
        )
        controller._on_table = [DurakCard('6D')]

        with self.assertRaises(exes.PlayerDoesNotHaveCard):
            controller.register_give_more([
                DurakCard('6S'), DurakCard('6H'), DurakCard('AC')
            ])

    def test_register_give_more_is_error_if_player_can_not_give_these_cards(self):
        controller = GameController()
        controller._state = controller.States.GIVING_MORE
        controller._no_response = True
        controller._to_move = controller._player1
        controller._trump = DurakCard('6H')
        controller._player1.cards = CardSet(
            cards=(DurakCard('AC'), DurakCard('AH'), DurakCard('6H')),
            trump=controller._trump
        )
        controller._on_table = [DurakCard('6D')]

        with self.assertRaises(exes.InvalidCard):
            controller.register_give_more([
                DurakCard('AC'), DurakCard('AH'), DurakCard('6H')
            ])

    def test_successful_register_give_more(self):
        controller = GameController()
        controller._state = controller.States.GIVING_MORE
        controller._no_response = True
        controller._to_move = controller._player1
        controller._deck = [DurakCard('JH')]
        controller._trump = DurakCard('6H')
        controller._player1.cards = CardSet(
            cards=(DurakCard('AC'), DurakCard('6S'), DurakCard('6H')),
            trump=controller._trump
        )
        controller._on_table = Table([DurakCard('6D')])

        controller.register_give_more([DurakCard('6S'), DurakCard('6H')])

        self.assertItemsEqual(controller._player1.cards, [DurakCard('AC')])
        self.assertSequenceEqual(controller._on_table, [DurakCard('6D')])
        self.assertItemsEqual(
            controller._on_table.given_more, [DurakCard('6S'), DurakCard('6H')]
        )
        self.assertEqual(controller._state, controller.States.DEALING)

    def test_deal_is_error_if_state_is_not_dealing(self):
        controller = GameController()
        controller._state = controller.States.MOVING
        with self.assertRaises(exes.InvalidAction):
            controller.deal()

    def test_deal_clears_the_table(self):
        controller = GameController()
        controller._state = controller.States.DEALING
        controller._no_response = True
        controller._discarded = []
        controller._to_move = controller._player1
        controller._player1.cards = set()
        controller._player2.cards = set()
        controller._deck = []
        controller._on_table = Table([DurakCard('6S'), DurakCard('6H')])
        controller._on_table.given_more = {DurakCard('7S'), DurakCard('7H')}

        controller.deal()

        self.assertSequenceEqual(controller._on_table, [])
        self.assertItemsEqual(controller._on_table.given_more, set())

    def test_deal_with_no_response(self):
        controller = GameController()
        controller._state = controller.States.DEALING
        controller._no_response = True
        controller._discarded = []
        controller._to_move = controller._player1
        controller._player1.cards = {DurakCard('JH')}
        controller._player2.cards = set()
        controller._deck = []
        controller._on_table = Table([DurakCard('6S'), DurakCard('6H')])
        controller._on_table.given_more = {DurakCard('7S'), DurakCard('7H')}

        controller.deal()

        self.assertItemsEqual(
            controller._player2.cards,
            {
                DurakCard('6S'),
                DurakCard('6H'),
                DurakCard('7S'),
                DurakCard('7H')
            }
        )
        self.assertFalse(controller._no_response)
        self.assertEqual(controller._to_move, controller._player1)
        self.assertEqual(controller._state, controller.States.MOVING)

    def test_deal_with_response(self):
        controller = GameController()
        controller._state = controller.States.DEALING
        controller._no_response = False
        controller._first_discard_completed = True
        controller._discarded = []
        controller._to_move = controller._player1
        controller._player1.cards = {DurakCard('JH')}
        controller._player2.cards = {DurakCard('JS')}
        controller._deck = []
        controller._on_table = Table([DurakCard('6S'), DurakCard('6H')])

        controller.deal()

        self.assertSequenceEqual(
            controller._discarded, [DurakCard('6S'), DurakCard('6H')]
        )
        self.assertEqual(controller._to_move, controller._player2)
        self.assertEqual(controller._state, controller.States.MOVING)

    def test_deal_sets_first_discard(self):
        controller = GameController()
        controller._state = controller.States.DEALING
        controller._no_response = False
        controller._first_discard_completed = False
        controller._discarded = []
        controller._to_move = controller._player1
        controller._player1.cards = set()
        controller._player2.cards = set()
        controller._deck = []
        controller._on_table = Table([DurakCard('6S'), DurakCard('6H')])

        controller.deal()

        self.assertTrue(controller._first_discard_completed)

    def test_deal_cards_and_return_value(self):
        controller = GameController()
        controller._state = controller.States.DEALING
        controller._no_response = False
        controller._first_discard_completed = True
        controller._discarded = []
        controller._to_move = controller._player1
        controller._player1.cards = {DurakCard('6S'), DurakCard('6H')}
        controller._player2.cards = {DurakCard('7S'), DurakCard('7H')}
        controller._deck = [
            DurakCard('AS'),
            DurakCard('AH'),
            DurakCard('KS'),
            DurakCard('KH'),
            DurakCard('QS'),
            DurakCard('QH'),
            DurakCard('JS'),
            DurakCard('JH'),
            DurakCard('TS'),
            DurakCard('TH'),
        ]
        controller._on_table = Table()

        return_value = controller.deal()

        self.assertItemsEqual(
            controller._player1.cards, [
                DurakCard('6S'),
                DurakCard('6H'),
                DurakCard('AS'),
                DurakCard('AH'),
                DurakCard('KS'),
                DurakCard('KH'),
            ]
        )
        self.assertItemsEqual(
            controller._player2.cards, [
                DurakCard('7S'),
                DurakCard('7H'),
                DurakCard('QS'),
                DurakCard('QH'),
                DurakCard('JS'),
                DurakCard('JH'),
            ]
        )
        self.assertSequenceEqual(
            controller._deck, [DurakCard('TS'), DurakCard('TH')]
        )
        self.assertDictEqual(return_value, {
            'player1_cards': controller._player1.cards,
            'player2_cards': controller._player2.cards
        })

    def test_deal_no_cards_needed(self):
        controller = GameController()
        controller._state = controller.States.DEALING
        controller._no_response = False
        controller._first_discard_completed = True
        controller._discarded = []
        controller._to_move = controller._player1
        controller._player1.cards = {
            DurakCard('6S'),
            DurakCard('6H'),
            DurakCard('8S'),
            DurakCard('8H'),
            DurakCard('9S'),
            DurakCard('9H')
        }
        controller._player2.cards = {DurakCard('7S'), DurakCard('7H')}
        controller._deck = [
            DurakCard('AS'),
            DurakCard('AH'),
            DurakCard('KS'),
            DurakCard('KH'),
            DurakCard('QS'),
            DurakCard('QH'),
            DurakCard('JS'),
            DurakCard('JH'),
            DurakCard('TS'),
            DurakCard('TH'),
        ]
        controller._on_table = Table()

        return_value = controller.deal()

        self.assertItemsEqual(
            controller._player1.cards, {
                DurakCard('6S'),
                DurakCard('6H'),
                DurakCard('8S'),
                DurakCard('8H'),
                DurakCard('9S'),
                DurakCard('9H')
            }
        )

    def test_winner_property(self):
        controller = GameController()
        given_list = [controller._player1, controller._player2, None]
        expected_list = [controller.PLAYER1, controller.PLAYER2, None]
        for given, expected in zip(given_list, expected_list):
            controller._winner = given
            self.assertEqual(controller.winner, expected)

    def test_on_table_property(self):
        controller = GameController()
        controller._on_table = [
            DurakCard('6S'), DurakCard('6H'), DurakCard('8S')
        ]
        self.assertEqual(controller.on_table, controller._on_table)
