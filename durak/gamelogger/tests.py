# -*- coding: utf-8 -*-
from cStringIO import StringIO
from datetime import datetime, timedelta
import json
import unittest

from mock import MagicMock, mock_open, patch

from durak.gamelogger import GameLogger, LogViewer
from durak.gamelogger.log_viewer import InvalidLogFormat
from durak.utils.cards import CardSet, DurakCard


class GameLoggerTest(unittest.TestCase):
    def setUp(self):
        self.logger = GameLogger()

    def assertAlmostNow(self, iso_datetime):
        now = datetime.now()
        dt = datetime.strptime(iso_datetime, '%Y-%m-%dT%H:%M:%S.%f')
        self.assertAlmostEqual(dt, now, delta=timedelta(seconds=2))

    def test_reset(self):
        self.logger._log = {'something': True}

        self.logger.reset()

        self.assertDictEqual(self.logger._log, {'moves': []})

    def test_log_before_game(self):
        self.logger.log_before_game(
            'name1', 'name2', [DurakCard('6H')], DurakCard('7H')
        )
        self.assertDictContainsSubset(
            {
                'player1_name': 'name1',
                'player2_name': 'name2',
                'deck': ['6H'],
                'opened_trump': '7H',
            },
            self.logger._log
        )
        self.assertAlmostNow(self.logger._log['started_at'])

    def test_log_after_game(self):
        self.logger.log_after_game(self.logger.PLAYER1)

        self.assertEqual(self.logger._log['result'], '1-0')
        self.assertAlmostNow(self.logger._log['ended_at'])

    def test_log_before_move(self):
        self.logger.log_before_move(
            [DurakCard('6H')], [DurakCard('7H')], self.logger.PLAYER1, 1
        )
        self.assertEqual(len(self.logger._log['moves']), 1)
        self.assertDictEqual(
            self.logger._log['moves'][0],
            {
                'player1_cards': ['6H'],
                'player2_cards': ['7H'],
                'to_move': self.logger.PLAYER1,
                'deck_count': 1,
            }
        )

    def test_log_after_move(self):
        self.logger._log['moves'].append({})
        self.logger.log_after_move(
            [DurakCard('6H'), DurakCard('7H')], {DurakCard('QH')}
        )

        self.assertEqual(len(self.logger._log['moves']), 1)
        self.assertDictEqual(
            self.logger._log['moves'][0],
            {'moves_and_responds': ['6H', '7H'], 'given_more': ['QH']}
        )

    def test_get_result(self):
        self.assertEqual(self.logger._get_result(self.logger.PLAYER1), '1-0')
        self.assertEqual(self.logger._get_result(self.logger.PLAYER2), '0-1')
        self.assertEqual(self.logger._get_result(None), 's-s')

    def test_log_title(self):
        self.logger.log_before_game(
            'name1', 'name2', [DurakCard('6H')], DurakCard('7H')
        )
        self.logger.log_after_game(self.logger.PLAYER2)

        self.assertEqual(
            self.logger._log_title,
            '%s, name1 - name2 (0-1)' % self.logger._log['started_at'].split('.')[0]
        )

    def test_write_to_file(self):
        filename = 'filename'
        self.logger.log_before_game(
            'name1', 'name2', [DurakCard('6H')], DurakCard('7H')
        )
        self.logger.log_after_game(self.logger.PLAYER2)

        open_mock = mock_open()
        with patch('__builtin__.open', open_mock, create=True):
            self.logger.write_to_file(filename)

            open_mock.assert_called_once_with(filename, 'a')
            open_mock().write.assert_called_once_with(
                '####%s####\n%s\n' % (
                    self.logger._log_title,
                    json.dumps(self.logger._log)
                )
            )

    def test_write_to_file_with_overwrite(self):
        filename = 'filename'
        self.logger.log_before_game(
            'name1', 'name2', [DurakCard('6H')], DurakCard('7H')
        )
        self.logger.log_after_game(self.logger.PLAYER2)

        open_mock = mock_open()
        with patch('__builtin__.open', open_mock, create=True):
            self.logger.write_to_file(filename, overwrite=True)

            open_mock.assert_called_once_with(filename, 'w')
            open_mock().write.assert_called_once_with(
                '####%s####\n%s\n' % (
                    self.logger._log_title,
                    json.dumps(self.logger._log)
                )
            )


class LogViewerTest(unittest.TestCase):
    FILENAME = 'filename'

    GAME0 = '{"moves": [{"to_move": "player1", "player1_cards": ["AS", "QS", "AH", "9D", "8D", "7H"], "moves_and_responds": ["7H", "TH"], "deck_count": 24, "player2_cards": ["JH", "TH", "QH", "6H", "8C", "TD"], "given_more": []}, {"to_move": "player2", "player1_cards": ["AS", "QC", "AH", "QS", "8D", "9D"], "moves_and_responds": ["6H"], "deck_count": 22, "player2_cards": ["6C", "QH", "6H", "8C", "TD", "JH"], "given_more": ["6C"]}], "ended_at": "2014-10-19T01:41:23.161425", "deck": ["QS", "8D", "AH", "AS", "7H", "9D", "TD", "JH", "QH", "TH", "8C", "6H", "QC", "6C", "JD", "9C", "9S", "KH", "AC", "8H", "KC", "8S", "TC", "7C", "TS", "9H", "6S", "6D", "7D", "JS", "KS", "AD", "KD", "JC", "QD", "7S"], "player2_name": "ENGINE", "result": "1-0", "player1_name": "HUMAN", "started_at": "2014-10-19T01:40:51.473966", "opened_trump": "7S"}'

    LOG_FILE_CONTENTS = '''\
####2014-10-19T01:40:51, HUMAN - ENGINE (1-0)####
%s
####2014-11-19T01:40:51, VOVAN - KOLYAN (1-0)####
{"moves": [{"to_move": "player1", "player1_cards": ["AS", "QS", "AH", "9D", "8D", "7H"], "moves_and_responds": ["7H", "TH"], "deck_count": 24, "player2_cards": ["JH", "TH", "QH", "6H", "8C", "TD"], "given_more": []}], "ended_at": "2014-10-19T01:41:23.161425", "deck": ["QS", "8D", "AH", "AS", "7H", "9D", "TD", "JH", "QH", "TH", "8C", "6H", "QC", "7C", "JD", "9C", "9S", "KH", "AC", "8H", "KC", "8S", "TC", "6C", "TS", "9H", "6S", "6D", "7D", "JS", "KS", "AD", "KD", "JC", "QD", "7S"], "player2_name": "KOLYAN", "result": "1-0", "player1_name": "VOVAN", "started_at": "2014-10-19T01:40:51.473966", "opened_trump": "7S"}
''' % GAME0

    def setUp(self):
        self.open_mock = MagicMock(spec=open)
        self._set_file_contents(self.LOG_FILE_CONTENTS)
        self.open_patcher = patch(
            '__builtin__.open', self.open_mock, create=True
        )
        self.open_patcher.start()

        self.log_viewer = LogViewer(self.FILENAME)

        self.game0 = json.loads(self.GAME0)

    def tearDown(self):
        self.open_patcher.stop()

    def _set_file_contents(self, contents):
        self.open_mock.return_value.__enter__.return_value = StringIO(contents)

    def test_fill_game_index_parsing(self):
        self.assertEqual(self.log_viewer._game_index, [
            {
                'prev_end_offset': 0,
                'start_offset': 50,
                'title': '2014-10-19T01:40:51, HUMAN - ENGINE (1-0)'
            },
            {
                'prev_end_offset': 874,
                'start_offset': 924,
                'title': '2014-11-19T01:40:51, VOVAN - KOLYAN (1-0)'
            },
        ])

    def test_io_error_in_fill_game_index_is_invalid_log_format_error(self):
        self.open_mock.side_effect = IOError

        with self.assertRaises(InvalidLogFormat):
            self.log_viewer._fill_game_index()

    def test_no_games_in_file_is_invalid_log_format_error(self):
        self._set_file_contents('no games for you')

        with self.assertRaises(InvalidLogFormat):
            self.log_viewer._fill_game_index()

    def test_iterindex_returns_iterator_over_game_index(self):
        self.assertItemsEqual(
            self.log_viewer.iterindex(), iter(self.log_viewer._game_index)
        )

    def test_load_game_loads_game_according_to_index(self):
        self.log_viewer.load_game(0)
        self.assertEqual(self.log_viewer.player1_name, 'HUMAN')

        self.log_viewer.load_game(1)
        self.assertEqual(self.log_viewer.player1_name, 'VOVAN')

    def test_io_error_in_load_game_is_invalid_log_format_error(self):
        self.open_mock.side_effect = IOError

        with self.assertRaises(InvalidLogFormat):
            self.log_viewer.load_game(0)

    def test_value_error_in_load_game_is_invalid_log_format_error(self):
        self._set_file_contents('no games for you')

        with self.assertRaises(InvalidLogFormat):
            self.log_viewer.load_game(0)

    def test_has_game_loaded_property(self):
        self.assertFalse(self.log_viewer.has_game_loaded)

        self.log_viewer.load_game(0)

        self.assertTrue(self.log_viewer.has_game_loaded)

    def test_get_new_move(self):
        self.log_viewer.load_game(0)

        move = self.game0['moves'][0]
        result = self.log_viewer._get_new_move(move)
        self.assertItemsEqual(result.keys(), move.keys() + ['event_type'])
        self.assertEqual(result['event_type'], self.log_viewer.NEW_MOVE)

    def test_opened_trump_property(self):
        self.log_viewer.load_game(0)

        self.assertEqual(
            self.log_viewer.opened_trump,
            DurakCard(self.game0['opened_trump'])
        )

    def test_to_game_start(self):
        self.log_viewer.load_game(0)

        self.log_viewer._current_move = 666
        self.log_viewer._current_table_index = 777

        self.log_viewer.to_game_start()

        self.assertEqual(
            self.log_viewer._current_move,
            self.log_viewer.INITIAL_CURRENT_MOVE
        )
        self.assertEqual(
            self.log_viewer._current_table_index,
            self.log_viewer.INITIAL_CURRENT_TABLE_INDEX
        )

    def test_to_game_end(self):
        self.log_viewer.load_game(0)

        self.log_viewer._current_move = 666
        self.log_viewer._current_table_index = 777

        self.log_viewer.to_game_end()

        self.assertEqual(
            self.log_viewer._current_move, len(self.game0['moves'])
        )
        self.assertEqual(
            self.log_viewer._current_table_index,
            self.log_viewer.INITIAL_CURRENT_TABLE_INDEX + 1
        )

    def test_player1_name_property(self):
        self.log_viewer.load_game(0)

        self.assertEqual(
            self.log_viewer.player1_name, self.game0['player1_name']
        )

    def test_player2_name_property(self):
        self.log_viewer.load_game(0)

        self.assertEqual(
            self.log_viewer.player2_name, self.game0['player2_name']
        )

    def test_get_opposite_player(self):
        self.assertEqual(
            self.log_viewer._get_opposite_player(self.log_viewer.PLAYER1),
            self.log_viewer.PLAYER2
        )
        self.assertEqual(
            self.log_viewer._get_opposite_player(self.log_viewer.PLAYER2),
            self.log_viewer.PLAYER1
        )

    def test_to_card_set(self):
        self.log_viewer.load_game(0)

        cards = ['AS', 'QS', 'AH', '9D', '8D', '7H']

        result = self.log_viewer._to_card_set(cards)
        self.assertTrue(isinstance(result, CardSet))
        self.assertItemsEqual(result, map(DurakCard, cards))
        self.assertEqual(result._trump, DurakCard(self.game0['opened_trump']))

    def test_has_next(self):
        self.log_viewer.load_game(0)
        self.assertTrue(self.log_viewer.has_next)

        self.log_viewer._current_move = 1
        self.log_viewer._current_table_index = 1
        self.assertTrue(self.log_viewer.has_next)

        self.log_viewer._current_table_index = 2
        self.assertFalse(self.log_viewer.has_next)

        self.log_viewer._current_move = 3
        self.log_viewer._current_table_index = (
            self.log_viewer.INITIAL_CURRENT_TABLE_INDEX
        )
        self.assertFalse(self.log_viewer.has_next)

    def test_has_prev(self):
        self.log_viewer._current_move = 666
        self.log_viewer._current_table_index = 777
        self.assertTrue(self.log_viewer.has_prev)

        self.log_viewer._current_move = self.log_viewer.INITIAL_CURRENT_MOVE
        self.assertTrue(self.log_viewer.has_prev)

        self.log_viewer._current_table_index = (
            self.log_viewer.INITIAL_CURRENT_TABLE_INDEX
        )
        self.assertFalse(self.log_viewer.has_prev)

    def test_get_next_and_get_prev(self):
        # проверяю оба метода в одном тесте, чтобы протестировать в условиях,
        # приближенных к реальным, а не городить моки
        EXPECTED_EVENTS = [
            {
                'to_move': self.log_viewer.PLAYER1,
                'event_type': self.log_viewer.NEW_MOVE,
                'moves_and_responds': [DurakCard('7H'), DurakCard('TH')],
                'deck_count': 24,
                'given_more': [],
                'player2_cards': set(map(DurakCard, (
                    '6H', '8C', 'JH', 'TH', 'QH', 'TD'
                ))),
                'player1_cards': set(map(DurakCard, (
                    'QS', 'AH', '9D', '8D', '7H', 'AS'
                ))),
            },
            {
                'to_move': self.log_viewer.PLAYER1,
                'event_type': self.log_viewer.MOVE,
                'card': DurakCard('7H'),
            },
            {
                'to_move': self.log_viewer.PLAYER2,
                'event_type': self.log_viewer.RESPOND,
                'card': DurakCard('TH'),
            },
            {
                'to_move': self.log_viewer.PLAYER2,
                'event_type': self.log_viewer.NEW_MOVE,
                'moves_and_responds': [DurakCard('6H')],
                'deck_count': 22,
                'given_more': [DurakCard('6C')],
                'player2_cards': set(map(DurakCard, (
                    '6H', '8C', 'JH', '6C', 'QH', 'TD'
                ))),
                'player1_cards': set(map(DurakCard, (
                    'QS', 'AH', '9D', '8D', 'QC', 'AS'
                ))),
            },
            {
                'to_move': self.log_viewer.PLAYER2,
                'event_type': self.log_viewer.MOVE,
                'card': DurakCard('6H'),
            },
            {
                'to_move': self.log_viewer.PLAYER2,
                'event_type': self.log_viewer.GIVE_MORE,
                'card': DurakCard('6C'),
            },
        ]

        self.log_viewer.load_game(0)

        expected = iter(EXPECTED_EVENTS)
        while self.log_viewer.has_next:
            log_event = self.log_viewer.get_next()
            self.assertEqual(log_event, next(expected))

        first_event = EXPECTED_EVENTS.pop(0)
        EXPECTED_EVENTS[2] = first_event
        expected = iter(reversed(EXPECTED_EVENTS))
        while self.log_viewer.has_prev:
            log_event = self.log_viewer.get_prev()
            self.assertEqual(log_event, next(expected))
