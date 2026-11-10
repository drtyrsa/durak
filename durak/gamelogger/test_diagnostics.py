"""Shared game logs remain replayable and preserve inputs needed for analysis."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from random import Random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from durak.autoplay import _play_game
from durak.gamelogger import LogViewer
from durak.gamelogger.__main__ import main as inspect_log
from durak.web.game import BrowserGame


def advance(browser):
    state = browser.snapshot()
    if not state['human_turn']:
        return browser.step(state['revision'])
    if state['phase'] == 'giving_more':
        action, cards = 'throw', state['legal_cards'][:state['max_throw']]
    elif state['legal_cards']:
        action, cards = 'play', state['legal_cards'][:1]
    else:
        action, cards = ('take' if state['phase'] == 'responding' else 'finish'), []
    return browser.action(action, cards, state['revision'])


def load(filename):
    viewer = LogViewer(filename)
    viewer.load_game(0)
    return viewer


class SharedDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = io.StringIO()
        stdout = redirect_stdout(self.output)
        stdout.__enter__()
        self.addCleanup(stdout.__exit__, None, None, None)

    def browser(self, engine='nextgen'):
        browser = BrowserGame(engine, log_dir=self.directory.name)
        self.addCleanup(browser.close)
        with patch('durak.controller.random', Random(31)):
            browser.start()
        return browser

    def external_dummy(self):
        launcher = Path(self.directory.name, 'external dummy')
        launcher.write_text('#!' + sys.executable + '\nimport sys\nsys.path.insert(0, ' +
                            repr(str(Path(__file__).resolve().parents[2])) + ')\n' +
                            'from durak.engine.dummy import main\nmain()\n')
        launcher.chmod(0o755)
        return launcher

    def test_complete_logs_replay_for_every_engine_including_external(self):
        launcher = self.external_dummy()
        for engine in ('dummy', 'nextgen', str(launcher)):
            with self.subTest(engine=engine):
                browser = self.browser(engine)
                for _ in range(1500):
                    if browser.controller.is_game_over():
                        break
                    advance(browser)
                else:
                    self.fail('game did not finish')
                viewer = load(browser.log_filename)
                self.assertEqual(len(list(viewer.iterindex())), 1)
                self.assertEqual({a['player'] for a in viewer.actions}, {'player1', 'player2'})
                played = []
                while viewer.has_next:
                    event = viewer.get_next()
                    if 'card' in event:
                        played.append(str(event['card']))
                self.assertCountEqual(played, [c for a in viewer.actions for c in a['cards']])
                for action in viewer.actions:
                    self.assertTrue(set(action['cards']) <= set(action['hand']))
                    self.assertEqual(action['on_table'], action['gamedata']['on_table'])
                if engine == 'nextgen':
                    details = [a['analysis'] for a in viewer.actions if a['player'] == 'player2']
                    self.assertTrue(details)
                    self.assertTrue(any(a['strategy'] == 'smart' for a in details))
                    self.assertTrue(any(a['strategy'] == 'exact' for a in details))
                else:
                    self.assertFalse(any('analysis' in a for a in viewer.actions))
                self.assertIn('result', json.loads(Path(browser.log_filename).read_text().splitlines()[1]))

    def test_autoplay_appends_one_replayable_entry_per_game(self):
        launcher = str(self.external_dummy())
        filename = str(Path(self.directory.name, 'matches.log'))
        for _ in range(2):
            _play_game(launcher, launcher, filename)
        viewer = LogViewer(filename)
        self.assertEqual(len(list(viewer.iterindex())), 2)
        for index in range(2):
            viewer.load_game(index)
            viewer.to_game_start()
            self.assertTrue(viewer.actions)
            while viewer.has_next:
                viewer.get_next()

    def test_live_and_abandoned_logs_are_readable_and_new_deal_gets_a_new_file(self):
        browser = self.browser('dummy')
        first = browser.log_filename
        initial = load(first)
        self.assertEqual(initial.actions, [])
        initial.get_next()  # a live empty table must be understood by the old viewer
        advance(browser)
        self.assertEqual(len(load(first).actions), 1)
        before = Path(first).read_text()
        with self.assertRaises(ValueError):
            browser.action('play', ['invalid'], browser.revision)
        self.assertEqual(Path(first).read_text(), before)
        browser.start()
        self.assertNotEqual(first, browser.log_filename)
        old = json.loads(Path(first).read_text().splitlines()[1])
        self.assertEqual(old['interruption_reason'], 'new_deal')
        self.assertNotIn('result', old)  # interruption is not a draw
        self.assertEqual(len(load(first).actions), 1)
        self.assertEqual(load(browser.log_filename).actions, [])

    def test_log_inspector_shows_any_engine_and_full_action(self):
        browser = self.browser('dummy')
        advance(browser)
        inspect_log([browser.log_filename])
        self.assertIn('#1 player', self.output.getvalue())
        output = io.StringIO()
        with redirect_stdout(output):
            inspect_log([browser.log_filename, '--action', '1'])
        action = json.loads(output.getvalue())
        self.assertEqual(action['gamedata']['deck_count'], 24)
        self.assertEqual(len(action['hand']), 6)

    def test_terminal_logging_works_with_dummy_too(self):
        result = subprocess.run([sys.executable, '-m', 'durak.play', '--engine', 'dummy',
                                 '--log-dir', self.directory.name], input='quit\n',
                                capture_output=True, text=True, check=True, timeout=10)
        self.assertIn('Game log:', result.stdout)
        self.assertEqual(result.stderr, '')
        files = list(Path(self.directory.name).glob('*.log'))
        self.assertEqual(len(files), 1)
        viewer = load(str(files[0]))
        self.assertTrue(viewer.has_next)
        self.assertEqual(viewer.player2_name, 'dummy')

    def test_snapshot_never_contains_diagnostics_or_opponent_hand(self):
        browser = self.browser()
        for _ in range(10):
            advance(browser)
        state = browser.snapshot()
        for field in ('analysis', 'log_filename', 'actions_log', 'opponent_hand', 'belief'):
            self.assertNotIn(field, state)

    def test_save_failure_keeps_previous_replay_and_does_not_break_play(self):
        browser = self.browser('dummy')
        original = Path(browser.log_filename).read_text()
        with patch.object(browser.controller._logger, 'write_snapshot', side_effect=OSError('disk full')):
            with self.assertWarnsRegex(RuntimeWarning, 'disk full'):
                advance(browser)
            advance(browser)  # no repeated warning/error on every move
        self.assertEqual(browser.controller.log_error, 'disk full')
        self.assertEqual(Path(browser.log_filename).read_text(), original)
        self.assertEqual(len(load(browser.log_filename).actions), 0)
