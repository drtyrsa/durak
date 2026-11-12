"""Exercise the browser's actual game flow and local HTTP API without wx."""
import http.client
import json
from pathlib import Path
from random import Random
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from durak.controller.exceptions import GameControllerError
from durak.engine.test_nextgen import game
from durak.utils.cards import CardSet, DurakCard
from durak.web.game import BrowserGame, StalePosition
from durak.web.server import DurakServer


def position(human, opponent, table=(), phase='moving', enemy_attacks=False):
    browser = BrowserGame('dummy')
    browser.start()
    browser.controller = game(human, opponent, table=table, phase=phase)
    if enemy_attacks:
        browser.controller._to_move = browser.controller._player2
    browser.hand = CardSet(human, '6S')
    browser.trump = DurakCard('6S')
    browser.taking = phase == 'giving_more'
    browser.engine.init('6S')
    browser.engine.deal(opponent, {})
    return browser


class BrowserGameTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js is optional; needed only for JavaScript tests')
    def test_luck_display_javascript(self):
        result = subprocess.run(['node', '--test', str(Path(__file__).with_name('test_luck_display.cjs'))],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_snapshot_hides_opponent_and_deck_cards(self):
        browser = BrowserGame()
        state = browser.start()
        self.assertEqual(set(state['hand']), set(map(str, browser.controller._player1.cards)))
        self.assertEqual(state['opponent_count'], 6)
        self.assertNotIn('opponent_hand', state)
        self.assertNotIn('player2_cards', state)
        self.assertNotIn('deck', state)
        self.assertNotIn('luck', state)
        self.assertEqual(state['deck_count'], 24)
        self.assertEqual(state['game_number'], 1)
        self.assertEqual(state['scores'], {'you': 0, 'opponent': 0, 'draw': 0})

    def test_cards_and_controls_follow_wx_turn_states(self):
        browser = position(['6C', '8S'], ['7C', '8D'])
        state = browser.snapshot()
        self.assertCountEqual(state['legal_cards'], ['6C', '8S'])
        self.assertEqual(state['actions'], [])
        with self.assertRaises(GameControllerError):
            browser.action('finish', [], state['revision'])
        state = browser.action('play', ['6C'], state['revision'])
        self.assertFalse(state['human_turn'])
        self.assertEqual(state['on_table'], ['6C'])
        self.assertEqual(state['hand'], ['8S'])
        with self.assertRaises(ValueError):
            browser.action('play', ['8S'], state['revision'])
        state = browser.step(state['revision'])
        self.assertEqual(state['on_table'], ['6C', '7C'])
        self.assertTrue(state['human_turn'])
        self.assertEqual(state['actions'], ['finish'])
        self.assertEqual(state['legal_cards'], [])
        state = browser.action('finish', [], state['revision'])
        self.assertEqual(state['phase'], 'dealing')
        state = browser.step(state['revision'])
        self.assertEqual(state['on_table'], [])
        self.assertFalse(state['human_turn'])
        self.assertEqual(state['game_number'], 1)

    def test_defence_take_and_throw_in_limits(self):
        browser = position(['6D', '6S', '7D'], ['8C', '9C'],
                           table=['6C', '7C', '6H'], phase='giving_more')
        state = browser.snapshot()
        self.assertCountEqual(state['legal_cards'], ['6D', '6S', '7D'])
        self.assertEqual(state['max_throw'], 1)
        with self.assertRaises(GameControllerError):
            browser.action('throw', ['6D', '6S'], state['revision'])
        self.assertEqual(browser.snapshot()['hand'], state['hand'])
        with self.assertRaises(ValueError):
            browser.action('throw', ['6D', '6D'], state['revision'])
        state = browser.action('throw', ['6S'], state['revision'])
        self.assertEqual(state['given_more'], ['6S'])
        self.assertEqual(state['phase'], 'dealing')
        state = browser.step(state['revision'])
        self.assertTrue(state['human_turn'])
        self.assertEqual(state['opponent_count'], 6)
        self.assertEqual(state['given_more'], [])

        browser = position(['7C', '8S', '9D'], ['7D'], table=['6C'],
                           phase='responding', enemy_attacks=True)
        state = browser.snapshot()
        self.assertCountEqual(state['legal_cards'], ['7C', '8S'])
        self.assertEqual(state['actions'], ['take'])
        state = browser.action('take', [], state['revision'])
        self.assertFalse(state['human_turn'])
        self.assertTrue(state['taking'])

    def test_last_card_draw_and_score_once(self):
        browser = position(['6C'], ['7C'])
        state = browser.action('play', ['6C'], browser.revision)
        self.assertFalse(state['game_over'])
        state = browser.step(state['revision'])
        self.assertTrue(state['game_over'])
        self.assertEqual(state['winner'], 'draw')
        self.assertEqual(state['scores']['draw'], 1)
        self.assertEqual(state['game_number'], 1)
        self.assertIsNone(browser.engine)
        self.assertEqual(browser.step(state['revision'])['scores']['draw'], 1)
        with patch.object(browser.controller, '_get_first_to_move_by_trump',
                          wraps=browser.controller._get_first_to_move_by_trump) as lowest:
            self.assertEqual(browser.start()['game_number'], 2)
        lowest.assert_called_once_with()
        self.assertEqual(browser.start()['game_number'], 3)

    def test_previous_winner_opens_next_deal_by_default(self):
        for winner in ('you', 'opponent'):
            with self.subTest(winner=winner):
                if winner == 'you':
                    browser = position(['6C'], ['7D'])
                    state = browser.action('play', ['6C'], browser.revision)
                else:
                    browser = position(['7D'], ['6C'], enemy_attacks=True)
                    state = browser.step(browser.revision)
                self.assertEqual(state['winner'], winner)
                with patch.object(browser.controller, '_get_first_to_move_by_trump') as lowest:
                    state = browser.start()
                lowest.assert_not_called()
                self.assertEqual(state['human_turn'], winner == 'you')
                self.assertEqual(state['scores'][winner], 1)

    def test_stale_or_invalid_moves_cannot_change_position(self):
        browser = position(['6C', '8S'], ['7C', '8D'])
        state = browser.snapshot()
        for action, cards in (('play', ['AH']), ('play', []), ('take', []), ('throw', [])):
            with self.assertRaises((GameControllerError, ValueError)):
                browser.action(action, cards, state['revision'])
            self.assertEqual(browser.snapshot(), state)
        browser.action('play', ['6C'], state['revision'])
        with self.assertRaises(StalePosition):
            browser.action('play', ['8S'], state['revision'])

    def test_cannot_launch_arbitrary_executables_from_browser(self):
        browser = BrowserGame()
        browser.start()
        with self.assertRaises(ValueError):
            browser.start('/bin/something')
        self.assertTrue(browser.started)
        self.assertEqual(browser.snapshot()['game_number'], 1)

    def test_complete_games_and_card_conservation(self):
        phases = set()
        for seed in range(16):
            browser = BrowserGame('nextgen' if seed % 2 else 'dummy')
            with patch('durak.controller.random', Random(seed)):
                state = browser.start()
            for _ in range(1500):
                controller = browser.controller
                cards = (list(controller._player1.cards) + list(controller._player2.cards)
                         + controller._deck + controller._discarded + controller.on_table
                         + list(controller._on_table.given_more))
                self.assertEqual(len(cards), 36)
                self.assertEqual(set(cards), DurakCard.all())
                self.assertEqual(set(state['hand']), set(map(str, controller._player1.cards)))
                if state['game_over']:
                    break
                self.assertNotIn('luck', state)
                if state['human_turn']:
                    phases.add(state['phase'])
                    if state['phase'] == 'giving_more':
                        action, cards = 'throw', state['legal_cards'][:state['max_throw']]
                    elif state['legal_cards']:
                        action, cards = 'play', [state['legal_cards'][0]]
                    else:
                        action, cards = ('take' if state['phase'] == 'responding' else 'finish'), []
                    state = browser.action(action, cards, state['revision'])
                else:
                    state = browser.step(state['revision'])
            else:
                self.fail('Game did not finish')
            self.assertEqual(sum(state['scores'].values()), 1)
            self.assertEqual(state['luck'], controller.luck_report())
            self.assertEqual(state['luck']['cards_drawn'], 24)
            self.assertAlmostEqual(state['luck']['total'],
                                   state['luck']['opening'] + state['luck']['refills'])
            self.assertNotIn('luck', browser.start())
        self.assertEqual(phases, {'moving', 'responding', 'giving_more'})

    def test_custom_engine_restarts_and_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'custom engine')
            path.write_text('#!' + sys.executable + '\nimport sys\nsys.path.insert(0, '
                            + repr(str(Path(__file__).resolve().parents[2]))
                            + ')\nfrom durak.engine.dummy import main\nmain()\n')
            path.chmod(0o755)
            browser = BrowserGame(str(path))
            try:
                state = browser.start()
                process = browser.engine._process
                self.assertEqual(state['engine'], 'custom')
                self.assertIn('custom', [item['id'] for item in state['engines']])
                browser.start()
                self.assertIsNotNone(process.poll())
                process = browser.engine._process
            finally:
                browser.close()
            self.assertIsNotNone(process.poll())


class WebHTTPTest(unittest.TestCase):
    def setUp(self):
        self.server = DurakServer(port=0, engine='dummy')
        self.server.game.start()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)

    def tearDown(self):
        self.connection.close()
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def call(self, path, data=None, headers=None):
        headers = headers or {}
        if data is None:
            self.connection.request('GET', path, headers=headers)
        else:
            headers = {'Content-Type': 'application/json', 'X-Durak-Token': self.server.token, **headers}
            self.connection.request('POST', path, body=json.dumps(data), headers=headers)
        response = self.connection.getresponse()
        body = response.read()
        return response.status, body

    def test_all_assets_are_served_and_no_directory_traversal(self):
        for path, contains in (('/', b'aria-label="Durak game table"'), ('/app.js', b'renderHand'),
                               ('/style.css', b'@media'), ('/favicon.svg', b'<svg')):
            status, body = self.call(path)
            self.assertEqual(status, 200)
            self.assertIn(contains, body)
        self.assertEqual(self.call('/../../setup.py')[0], 404)

    def test_new_game_revision_and_json_validation(self):
        status, body = self.call('/api/state')
        state = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(state['token'], self.server.token)
        status, body = self.call('/api/new', {'engine': 'nextgen', 'revision': state['revision']})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['engine'], 'nextgen')
        state_after_change = json.loads(body)
        status, body = self.call('/api/new', {'revision': state_after_change['revision']})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['engine'], 'nextgen')
        self.assertEqual(json.loads(body)['game_number'], state_after_change['game_number'] + 1)
        self.assertEqual(self.call('/api/new', {'engine': 'dummy', 'revision': state['revision']})[0], 409)
        self.assertEqual(self.call('/api/new', {'engine': '/bin/anything', 'revision': self.server.game.revision})[0], 400)
        self.assertEqual(self.call('/api/action', {'cards': '6C', 'revision': self.server.game.revision})[0], 400)
        self.assertEqual(self.call('/api/new', [1, 2])[0], 400)

    def test_cross_origin_and_missing_tokens_rejected(self):
        self.assertEqual(self.call('/api/state', headers={'Host': 'untrusted.example'})[0], 403)
        self.assertEqual(self.call('/api/new', {}, {'Origin': 'https://untrusted.example'})[0], 403)
        self.assertEqual(self.call('/api/new', {}, {'X-Durak-Token': ''})[0], 403)

    def test_engine_error_is_recoverable(self):
        browser = self.server.game
        browser.controller._to_move = browser.controller._player2
        with patch.object(browser.engine, 'move', side_effect=OSError('test engine failure')):
            status, body = self.call('/api/step', {'revision': browser.revision})
        self.assertEqual(status, 502)
        self.assertIn('test engine failure', json.loads(body)['error'])
        status, body = self.call('/api/new', {'engine': 'dummy', 'revision': browser.revision})
        self.assertEqual(status, 200)
        self.assertIsNone(json.loads(body)['error'])


if __name__ == '__main__':
    unittest.main()
