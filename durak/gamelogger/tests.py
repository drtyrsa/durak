# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
import json
import unittest

from mock import mock_open, patch

from durak.gamelogger import GameLogger
from durak.utils.cards import DurakCard


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
