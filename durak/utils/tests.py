# -*- coding: utf-8 -*-
import json
import os
import unittest

from mock import mock_open, patch

from durak.consts import HOME_DIR
from durak.utils import get_filename, get_setting, set_setting
from durak.utils.cards import DurakCard, CardSet


class DurakCardTest(unittest.TestCase):

    def test_new_accepts_positional_arguments(self):
        card = DurakCard('6', 'H')
        self.assertEqual(card.numeric_rank, 0)  # first elem of DurakCard.RANKS
        self.assertEqual(card.suit, 'H')

    def test_new_accepts_keyword_arguments(self):
        card = DurakCard(rank='6', suit='H')
        self.assertEqual(card.numeric_rank, 0)  # first elem of DurakCard.RANKS
        self.assertEqual(card.suit, 'H')

    def test_new_accepts_strings(self):
        card = DurakCard('6H')
        self.assertEqual(card.numeric_rank, 0)  # first elem of DurakCard.RANKS
        self.assertEqual(card.suit, 'H')

    def test_new_raises_exception_on_not_2_chars_length_string(self):
        with self.assertRaises(ValueError):
            DurakCard('6')

    def test_new_raises_exception_on_invalid_set_of_arguments(self):
        with self.assertRaises(ValueError):
            DurakCard('6', 'H', some='thing')

        with self.assertRaises(ValueError):
            DurakCard(rank='6')

    def test_new_raises_exception_on_invalid_suit(self):
        with self.assertRaises(ValueError):
            DurakCard('6', 'L')

    def test_new_raises_exception_on_invalid_rank(self):
        with self.assertRaises(ValueError):
            DurakCard('0', 'H')

    def test_numeric_rank_is_index_in_ranks(self):
        for index, rank in enumerate(DurakCard.RANKS):
            card = DurakCard(rank, 'H')
            self.assertEqual(card.numeric_rank, index)

    def test_rank_is_rank_from_new(self):
        for rank in DurakCard.RANKS:
            card = DurakCard(rank, 'H')
            self.assertEqual(card.rank, rank)

    def test_suit_is_suit_from_new(self):
        for suit in DurakCard.SUITS:
            card = DurakCard('6', suit)
            self.assertEqual(card.suit, suit)

    def test_all(self):
        expected = set()
        for rank in DurakCard.RANKS:
            for suit in DurakCard.SUITS:
                expected.add(DurakCard(rank, suit))
        self.assertEqual(DurakCard.all(), expected)

    def test_str(self):
        card = DurakCard('6', 'H')
        self.assertEqual(str(card), '6H')

        card = DurakCard('T', 'S')
        self.assertEqual(str(card), 'TS')

        card = DurakCard('A', 'D')
        self.assertEqual(str(card), 'AD')

    def test_hash(self):
        card = DurakCard('6', 'H')
        self.assertEqual(hash(card), hash('6H'))

        card = DurakCard('T', 'S')
        self.assertEqual(hash(card), hash('TS'))

        card = DurakCard('A', 'D')
        self.assertEqual(hash(card), hash('AD'))

        some_set = {
            DurakCard('6', 'H'), DurakCard('6', 'H'), DurakCard('6', 'H')
        }
        self.assertEqual(len(some_set), 1)

    def test_durak_cards_can_not_be_compared_with_objs_of_other_class(self):
        card = DurakCard('6', 'H')
        with self.assertRaises(ValueError):
            card > None

        with self.assertRaises(ValueError):
            card < 7

        with self.assertRaises(ValueError):
            card == object()

    def test_cards_of_same_suit_are_compared_by_rank(self):
        card = DurakCard('T', 'H')
        self.assertTrue(card > DurakCard('6', 'H'))
        self.assertTrue(card < DurakCard('K', 'H'))
        self.assertEqual(card, DurakCard('T', 'H'))

    def test_cards_of_different_suits_are_never_equal(self):
        self.assertNotEqual(DurakCard('6', 'S'), DurakCard('6', 'H'))
        self.assertNotEqual(DurakCard('6', 'C'), DurakCard('6', 'D'))

    def test_durak_card_instances_are_cached(self):
        DurakCard._INSTANCE_REGISTRY.pop((0, 'H'), None)
        self.assertFalse((0, 'H') in DurakCard._INSTANCE_REGISTRY)

        card = DurakCard('6', 'H')
        self.assertTrue((0, 'H') in DurakCard._INSTANCE_REGISTRY)
        self.assertEqual(card.rank, '6')
        self.assertEqual(card.suit, 'H')

        # making sure it's really being retrieved from cache
        DurakCard._INSTANCE_REGISTRY[(0, 'H')] = 'banana'
        card = DurakCard('6', 'H')
        self.assertEqual(card, 'banana')

        # let's remove invalid value from global cache
        DurakCard._INSTANCE_REGISTRY.pop((0, 'H'), None)

    def test_durak_card_instances_are_immutable(self):
        card = DurakCard('7', 'S')

        with self.assertRaises(AttributeError):
            card.rank = '8'

        with self.assertRaises(AttributeError):
            card.suit = 'D'


class CardSetTest(unittest.TestCase):

    def setUp(self):
        self.trump = DurakCard('6', 'H')

    def test_init_accepts_cards_and_trump(self):
        cards = [
            DurakCard('7', 'S'),
            'TD',
            DurakCard('KC')
        ]
        card_set = CardSet(cards, self.trump)
        self.assertEqual(card_set._trump, self.trump)
        self.assertItemsEqual(card_set, {
            DurakCard('7S'), DurakCard('TD'), DurakCard('KC')
        })

    def test_is_trump(self):
        card_set = CardSet([], self.trump)
        self.assertTrue(card_set._is_trump('7H'))
        self.assertFalse(card_set._is_trump('8S'))
        self.assertFalse(card_set._is_trump('9C'))
        self.assertFalse(card_set._is_trump('TD'))

    def test_trumps(self):
        card_set = CardSet(['7H', '8S', '9C', 'TD', '6H'], self.trump)
        self.assertEqual(card_set.trumps(), {DurakCard('6H'), DurakCard('7H')})

    def test_not_trumps(self):
        card_set = CardSet(['7H', '8S', '9C', 'TD', '6H'], self.trump)
        self.assertEqual(
            card_set.not_trumps(),
            {DurakCard('8S'), DurakCard('9C'), DurakCard('TD')}
        )

    def test_sorted_cards_returns_trumps_last(self):
        card_set = CardSet(['7H', '8S', 'TC', '9C', '6H'], self.trump)
        self.assertEqual(card_set.sorted_cards(), [
            DurakCard('8S'),
            DurakCard('9C'),
            DurakCard('TC'),
            DurakCard('6H'),
            DurakCard('7H'),
        ])

    def test_card_groups_including_trumps(self):
        card_set = CardSet(
            ['7H', '8S', '8C', '9C', '6H', '6C', '6D'], self.trump
        )
        self.assertEqual(card_set.card_groups(), [
            {DurakCard('6H'), DurakCard('6C'), DurakCard('6D')},
            {DurakCard('8S'), DurakCard('8C')},
        ])

    def test_card_groups_not_including_trumps(self):
        card_set = CardSet(
            ['7H', '8S', '8C', '9C', '6H', '6C', '6D'], self.trump
        )
        self.assertEqual(card_set.card_groups(including_trumps=False), [
            {DurakCard('6C'), DurakCard('6D')},
            {DurakCard('8S'), DurakCard('8C')},
        ])

    def test_cards_that_can_beat_trump_including_trumps(self):
        card_set = CardSet(
            ['7H', 'KH', 'AH', '6S', 'TS', 'QS', '8D', 'AC'], self.trump
        )
        self.assertEqual(card_set.cards_that_can_beat('TH'), [
            DurakCard('KH'), DurakCard('AH'),
        ])

    def test_cards_that_can_beat_trump_not_including_trumps(self):
        card_set = CardSet(
            ['7H', 'KH', 'AH', '6S', 'TS', 'QS', '8D', 'AC'], self.trump
        )
        results = card_set.cards_that_can_beat('TH', including_trumps=False)
        self.assertEqual(results, [])

    def test_cards_that_can_beat_not_trump_including_trumps(self):
        card_set = CardSet(
            ['7H', 'KH', 'AH', '6S', 'TS', 'QS', '8D', 'AC'], self.trump
        )
        self.assertEqual(card_set.cards_that_can_beat('8S'), [
            DurakCard('TS'),
            DurakCard('QS'),
            DurakCard('7H'),
            DurakCard('KH'),
            DurakCard('AH'),
        ])

    def test_cards_that_can_beat_not_trump_not_including_trumps(self):
        card_set = CardSet(
            ['7H', 'KH', 'AH', '6S', 'TS', 'QS', '8D', 'AC'], self.trump
        )
        results = card_set.cards_that_can_beat('8S', including_trumps=False)
        self.assertEqual(results, [DurakCard('TS'), DurakCard('QS')])

    def test_cards_that_can_be_added_to_including_trumps(self):
        card_set = CardSet(
            ['7H', '7S', 'AH', 'AD', 'TS', 'QS', '8D', 'AC'], self.trump
        )
        results = card_set.cards_that_can_be_added_to(['9C', '7D', 'AS'])
        self.assertEqual(results, [
            DurakCard('7S'),
            DurakCard('AC'),
            DurakCard('AD'),
            DurakCard('7H'),
            DurakCard('AH'),
        ])

    def test_cards_that_can_be_added_to_not_including_trumps(self):
        card_set = CardSet(
            ['7H', '7S', 'AH', 'AD', 'TS', 'QS', '8D', 'AC'], self.trump
        )
        results = card_set.cards_that_can_be_added_to(
            ['9C', '7D', 'AS'], including_trumps=False
        )
        self.assertEqual(results, [
            DurakCard('7S'),
            DurakCard('AC'),
            DurakCard('AD'),
        ])

    def test_cards_that_can_be_added_to_returns_all_cards_if_to_is_empty(self):
        card_set = CardSet(
            ['7H', '7S', 'AH', 'AD', 'TS', 'QS', '8D', 'AC'], self.trump
        )
        results = card_set.cards_that_can_be_added_to([])
        self.assertEqual(results, card_set.sorted_cards())

    def test_lowest_trump(self):
        card_set = CardSet(
            ['7S', 'AH', 'AD', 'TS', '7H', 'QS', '8D', 'AC'], self.trump
        )
        self.assertEqual(card_set.lowest_trump(), DurakCard('7H'))

    def test_lowest_trump_is_none_if_no_trumps(self):
        card_set = CardSet(
            ['7S', 'AD', 'TS', 'QS', '8D', 'AC'], self.trump
        )
        self.assertTrue(card_set.lowest_trump() is None)


class GetFilenameFunctionTest(unittest.TestCase):
    def setUp(self):
        self.filename = 'filename'
        self.expected = os.path.join(
            os.path.expanduser('~'), HOME_DIR, self.filename
        )

    def test_path_is_just_joined_if_parent_dir_exists(self):
        with patch.object(os, 'makedirs') as makedirs_mock:
            with patch.object(os.path, 'exists', return_value=True):
                result = get_filename(self.filename)
                self.assertEqual(result, self.expected)
                self.assertFalse(makedirs_mock.called)

    def test_parent_dir_is_created_if_does_not_exist(self):
        with patch.object(os, 'makedirs') as makedirs_mock:
            with patch.object(os.path, 'exists', return_value=False):
                result = get_filename(self.filename)
                self.assertEqual(result, self.expected)
                self.assertTrue(makedirs_mock.called)


class GetSettingFunctionTest(unittest.TestCase):
    SETTING_NAME = 'some_setting'
    DEFAULT = 'default'
    VALUE = 'some_value'

    def setUp(self):
        self.open_mock = mock_open(read_data=json.dumps(
            {self.SETTING_NAME: self.VALUE}
        ))
        self._open_patcher = patch(
            '__builtin__.open', self.open_mock, create=True
        )
        self._open_patcher.start()

        self._makedirs_patcher = patch.object(os, 'makedirs')
        self._makedirs_patcher.start()

    def tearDown(self):
        self._open_patcher.stop()
        self._makedirs_patcher.stop()

    def test_if_file_does_not_exist_default_is_returned(self):
        with patch.object(os.path, 'exists', return_value=False):
            result = get_setting(self.SETTING_NAME, self.DEFAULT)

        self.assertEqual(result, self.DEFAULT)
        self.assertFalse(self.open_mock.called)

    def test_if_key_exists_in_json_it_is_returned(self):
        with patch.object(os.path, 'exists', return_value=True):
            result = get_setting(self.SETTING_NAME, self.DEFAULT)

        self.assertEqual(result, self.VALUE)
        self.assertTrue(self.open_mock.called)

    def test_if_key_does_not_exist_in_json_default_is_returned(self):
        with patch.object(os.path, 'exists', return_value=True):
            result = get_setting('another_setting', self.DEFAULT)

        self.assertEqual(result, self.DEFAULT)
        self.assertTrue(self.open_mock.called)


class SetSettingFunctionTest(unittest.TestCase):
    SETTING_NAME = 'some_setting'
    VALUE = 'some_value'

    def setUp(self):
        self.open_mock = mock_open(read_data=json.dumps(
            {self.SETTING_NAME: 'old_value', 'some': 'other'}
        ))
        self._open_patcher = patch(
            '__builtin__.open', self.open_mock, create=True
        )
        self._open_patcher.start()

        self._makedirs_patcher = patch.object(os, 'makedirs')
        self._makedirs_patcher.start()

    def tearDown(self):
        self._open_patcher.stop()
        self._makedirs_patcher.stop()

    def test_if_file_does_not_exist_it_is_created(self):
        with patch.object(os.path, 'exists', return_value=False):
            with patch.object(json, 'dump') as dump_mock:
                set_setting(self.SETTING_NAME, self.VALUE)

        dump_mock.assert_called_once_with(
            {self.SETTING_NAME: self.VALUE}, self.open_mock()
        )

    def test_if_file_exists_json_is_updated(self):
        with patch.object(os.path, 'exists', return_value=True):
            with patch.object(json, 'dump') as dump_mock:
                set_setting(self.SETTING_NAME, self.VALUE)

        dump_mock.assert_called_once_with(
            {self.SETTING_NAME: self.VALUE, 'some': 'other'}, self.open_mock()
        )
