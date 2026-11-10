"""Terminal play tests: no display server or wxPython required."""
import unittest
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import Mock, patch

from durak.engine.nextgen import NextGenEngine
from durak.engine.test_nextgen import game
from durak.engine.wrapper import EngineWrapper, EngineWrapperException
from durak.play import main, play


class TerminalPlayTest(unittest.TestCase):
    def play_position(self, controller, inputs, engine=None):
        data = {'trump': controller._trump,
                'player1_cards': controller._player1.cards.copy(),
                'player2_cards': controller._player2.cards.copy()}
        messages = []
        with patch.object(controller, 'start_new_game', return_value=data):
            result = play(engine or NextGenEngine(), read=lambda prompt: next(inputs),
                          write=messages.append, controller=controller)
        return result, messages

    def test_complete_game_and_invalid_input(self):
        controller = game(['6C'], ['7C'])
        _, messages = self.play_position(controller, iter(['invalid', '6C 7C', '', '6c']))
        self.assertTrue(controller.is_game_over())
        self.assertIsNone(controller.winner)
        self.assertEqual(messages[-1], 'Draw!')
        self.assertEqual(sum(line.startswith('Invalid action:') for line in messages), 3)

    def test_quit(self):
        controller = game(['6C'], ['7C'])
        _, messages = self.play_position(controller, iter(['quit']))
        self.assertFalse(controller.is_game_over())
        self.assertEqual(messages[-1], 'Game ended.')

    def test_eof(self):
        def inputs():
            raise EOFError
            yield
        controller = game(['6C'], ['7C'])
        _, messages = self.play_position(controller, inputs())
        self.assertFalse(controller.is_game_over())
        self.assertIn('Game ended.', messages[-1])

    def test_builtin_selection(self):
        for args, name in (([], 'NextGenEngine'), (['--engine', 'dummy'], 'DummyEngine')):
            with patch('durak.play.' + name) as factory, patch('durak.play.play') as run:
                main(args)
                run.assert_called_once_with(factory.return_value)

    def test_external_engine_cleanup_on_finish_quit_and_error(self):
        for error in (None, EngineWrapperException('bad engine'), KeyboardInterrupt()):
            engine = Mock(spec=EngineWrapper)
            with patch('durak.play.EngineWrapper', return_value=engine) as factory, \
                    patch('durak.play.play', side_effect=error), \
                    patch('sys.stderr', new_callable=io.StringIO):
                if error is None:
                    main(['--engine', '/custom engine'])
                elif isinstance(error, KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        main(['--engine', '/custom engine'])
                else:
                    with self.assertRaises(SystemExit) as caught:
                        main(['--engine', '/custom engine'])
                    self.assertEqual(caught.exception.code, 1)
                factory.assert_called_once_with('/custom engine')
                engine.game_end.assert_called_once_with()


class ExternalEnginePlayTest(unittest.TestCase):
    play_position = TerminalPlayTest.play_position

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.executable = Path(cls.directory.name, 'dummy engine')
        cls.executable.write_text(
            '#!' + sys.executable + '\n'
            'import sys\n'
            'sys.path.insert(0, ' + repr(str(Path(__file__).resolve().parents[1])) + ')\n'
            'from durak.engine.dummy import main\n'
            'main()\n')
        cls.executable.chmod(0o755)

    def test_protocol_actions_in_real_games(self):
        cases = [
            # A single-card response, a take, a pass, and multiple throw-ins.
            (game(['6C'], ['7C']), False, ['6C'], 'Opponent respond: 7C'),
            (game(['6C', '8D'], ['6H']), False, ['6C', '', '8D'], 'Opponent respond: take'),
            (game(['7D'], ['6C'], table=['8D', '9D']), True, ['7D'], 'Opponent move: stop'),
            (game(['7H', '8H', '9H'], ['6C', '6D'], table=['6H'], phase='giving_more'),
             True, [], 'Opponent give_more: 6C 6D'),
            (game(['7D'], ['6C'], table=['8D'], phase='giving_more'),
             True, [], 'Opponent give_more: nothing'),
        ]
        for controller, switch, inputs, expected in cases:
            with self.subTest(expected=expected):
                if switch:
                    controller._to_move = controller._player2
                engine = EngineWrapper(str(self.executable))
                process = engine._process
                try:
                    _, messages = self.play_position(controller, iter(inputs), engine)
                    self.assertTrue(controller.is_game_over())
                    self.assertIn(expected, messages)
                finally:
                    engine.game_end()
                self.assertIsNotNone(process.poll())
                self.assertTrue(process.stdin.closed)
                self.assertTrue(process.stdout.closed)

    def test_cli_accepts_path_with_spaces_and_name_on_path(self):
        env = dict(os.environ, PATH=self.directory.name + os.pathsep + os.environ.get('PATH', ''))
        for executable in (str(self.executable), self.executable.name):
            result = subprocess.run([sys.executable, '-m', 'durak.play', '--engine', executable],
                                    input='quit\n', text=True, capture_output=True, timeout=10,
                                    check=True, env=env)
            self.assertIn('Game ended.', result.stdout)
            self.assertEqual(result.stderr, '')

    def test_missing_executable_reports_a_clear_error(self):
        result = subprocess.run([sys.executable, '-m', 'durak.play', '--engine',
                                 str(Path(self.directory.name, 'does-not-exist'))],
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Engine error:', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
