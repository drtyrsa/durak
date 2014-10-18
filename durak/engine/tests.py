# -*- coding: utf-8 -*-
import unittest

from mock import patch

from durak.utils.cards import DurakCard
from durak.engine.base import BaseEngine
from durak.engine.wrapper import EngineWrapper, EngineWrapperException


class BaseEngineTest(unittest.TestCase):

    def setUp(self):
        self.engine = BaseEngine()
        self.engine.only_one_iteration = True
        self._sys_patcher = patch('durak.engine.base.sys')
        sys_mock = self._sys_patcher.start()
        self.stdin_mock = sys_mock.stdin
        self.stdout_mock = sys_mock.stdout

    def tearDown(self):
        self._sys_patcher.stop()

    def test_not_implemented_methods(self):
        with self.assertRaises(NotImplementedError):
            self.engine.init(None)

        other_methods = ['deal', 'move', 'respond', 'give_more']
        for method_name in other_methods:
            method = getattr(self.engine, method_name)
            with self.assertRaises(NotImplementedError):
                method(None, None)

    def test_output_prints_line_and_flushes_stdout(self):
        SOME_LINE = 'some_line'
        self.engine._output(SOME_LINE)

        self.stdout_mock.write.assert_called_once_with(SOME_LINE + '\n')
        self.assertTrue(self.stdout_mock.flush.called)

    def test_parse_line_loads_gamedata_if_present(self):
        LINE = 'command ## {"some": "value"}'
        command_name, args, gamedata = self.engine._parse_line(LINE)
        self.assertEqual(command_name, 'command')
        self.assertDictEqual(gamedata, {'some': 'value'})

    def test_parse_line_without_gamedata_is_ok_too(self):
        LINE = 'command'
        command_name, args, gamedata = self.engine._parse_line(LINE)
        self.assertEqual(command_name, 'command')
        self.assertDictEqual(gamedata, {})

    def test_parse_line_loads_args(self):
        LINE = 'command arg1 arg2 arg3'
        command_name, args, gamedata = self.engine._parse_line(LINE)
        self.assertEqual(command_name, 'command')
        self.assertEqual(args, ['arg1', 'arg2', 'arg3'])

    def test_command_calling(self):
        self.stdin_mock.readline.return_value = 'init trump1'
        with patch.object(self.engine, 'init') as init_mock:
            init_mock.return_value = 'some'
            self.engine.run()
            init_mock.assert_called_once_with('trump1')
            self.stdout_mock.write.assert_called_with('some\n')

        other_methods = ['deal', 'move', 'respond', 'give_more']
        for method_name in other_methods:
            self.stdin_mock.readline.return_value = (
                '%s arg1 arg2 arg3 ## {"some": "value"}' % method_name
            )
            with patch.object(self.engine, method_name) as method_mock:
                method_mock.return_value = method_name
                self.engine.run()
                method_mock.assert_called_once_with(
                    ['arg1', 'arg2', 'arg3'], gamedata={'some': 'value'}
                )
                self.stdout_mock.write.assert_called_with(
                    method_name + '\n'
                )

    def test_game_end_command(self):
        self.stdin_mock.readline.return_value = 'game_end'
        self.engine.run()
        self.assertFalse(self.stdout_mock.write.called)

    def test_unknown_command(self):
        self.stdin_mock.readline.return_value = 'hahaha arg1 arg2'
        self.engine.run()
        self.stdout_mock.write.assert_called_once_with(
            'Error: Unknown command "hahaha"\n'
        )


class EngineWrapperTest(unittest.TestCase):

    def setUp(self):
        self._subprocess_patcher = patch('durak.engine.wrapper.subprocess')
        self.subprocess_mock = self._subprocess_patcher.start()
        self.process = self.subprocess_mock.Popen.return_value
        self.process.stdout.readline.return_value = 'ok'

        self.wrapper = EngineWrapper('path_to_engine')

    def tearDown(self):
        self._subprocess_patcher.stop()

    def test_popen_arguments(self):
        _ = EngineWrapper('path_to_engine')
        self.subprocess_mock.Popen.assert_called_with(
            'path_to_engine',
            stdin=self.subprocess_mock.PIPE,
            stdout=self.subprocess_mock.PIPE
        )

    def test_write_outputs_stripped_line_plus_break(self):
        self.wrapper._write('hi there!    ')
        self.process.stdin.write.assert_called_once_with('hi there!\n')

    def test_write_command_without_gamedata(self):
        self.wrapper._write_command('init', [DurakCard('AH')])
        self.process.stdin.write.assert_called_once_with('init AH\n')

    def test_write_command_with_gamedata(self):
        self.wrapper._write_command(
            'init', [DurakCard('AH')], gamedata={'some': 'value'}
        )
        self.process.stdin.write.assert_called_once_with(
            'init AH ## {"some": "value"}\n'
        )

    def test_write_command_without_cards(self):
        self.wrapper._write_command('move', [])
        self.process.stdin.write.assert_called_once_with('move\n')

    def test_get_output(self):
        self.process.stdout.readline.return_value = 'hi there!   '
        self.assertEqual(self.wrapper._get_output(), 'hi there!')

    def test_game_end_finishes_game_and_kills_process(self):
        self.assertFalse(self.wrapper._process is None)

        self.wrapper.game_end()

        self.assertTrue(self.process.kill.called)
        self.process.stdin.write.assert_called_once_with('game_end\n')
        self.assertTrue(self.wrapper._process is None)

    def test_game_end_is_idempotent(self):
        self.assertFalse(self.wrapper._process is None)

        self.wrapper.game_end()

        self.assertTrue(self.process.kill.called)
        self.assertTrue(self.wrapper._process is None)

        self.wrapper.game_end()
        self.assertTrue(self.wrapper._process is None)

    def test_init_writes_command_and_reads_output(self):
        self.wrapper.init(DurakCard('7H'))

        self.process.stdin.write.assert_called_once_with('init 7H\n')
        self.assertTrue(self.process.stdout.readline.called)

    def test_init_raises_exception_if_engine_response_is_not_ok(self):
        self.process.stdout.readline.return_value = 'error!'
        with self.assertRaises(EngineWrapperException):
            self.wrapper.init(DurakCard('7H'))

    def test_deal_writes_command_and_reads_output(self):
        self.wrapper.deal([DurakCard('7H'), DurakCard('8H')])

        self.process.stdin.write.assert_called_once_with('deal 7H 8H\n')
        self.assertTrue(self.process.stdout.readline.called)

    def test_deal_raises_exception_if_engine_response_is_not_ok(self):
        self.process.stdout.readline.return_value = 'error!'
        with self.assertRaises(EngineWrapperException):
            self.wrapper.deal([DurakCard('7H'), DurakCard('8H')])

    def test_move_converts_output_to_card(self):
        self.process.stdout.readline.return_value = '8S'

        result = self.wrapper.move([DurakCard('7H'), DurakCard('8H')])

        self.assertEqual(result, DurakCard('8S'))
        self.process.stdin.write.assert_called_once_with('move 7H 8H\n')
        self.assertTrue(self.process.stdout.readline.called)

    def test_move_returns_none_if_no_output_given(self):
        self.process.stdout.readline.return_value = ''

        result = self.wrapper.move([DurakCard('7H'), DurakCard('8H')])

        self.assertTrue(result is None)
        self.process.stdin.write.assert_called_once_with('move 7H 8H\n')
        self.assertTrue(self.process.stdout.readline.called)

    def test_move_raises_exception_if_cant_convert_output_to_card(self):
        self.process.stdout.readline.return_value = 'error'
        with self.assertRaises(EngineWrapperException):
            self.wrapper.move([DurakCard('7H'), DurakCard('8H')])

    def test_respond_converts_output_to_card(self):
        self.process.stdout.readline.return_value = '8H'

        result = self.wrapper.respond([DurakCard('7H')])

        self.assertEqual(result, DurakCard('8H'))
        self.process.stdin.write.assert_called_once_with('respond 7H\n')
        self.assertTrue(self.process.stdout.readline.called)

    def test_respond_returns_none_if_no_output_given(self):
        self.process.stdout.readline.return_value = ''

        result = self.wrapper.respond([DurakCard('7H')])

        self.assertTrue(result is None)
        self.process.stdin.write.assert_called_once_with('respond 7H\n')
        self.assertTrue(self.process.stdout.readline.called)

    def test_respond_raises_exception_if_cant_convert_output_to_card(self):
        self.process.stdout.readline.return_value = 'error'
        with self.assertRaises(EngineWrapperException):
            self.wrapper.respond([DurakCard('7H')])

    def test_give_more_converts_output_to_cards(self):
        self.process.stdout.readline.return_value = '8H 9H'

        results = self.wrapper.give_more([DurakCard('7H')])

        self.assertItemsEqual(results, [DurakCard('8H'), DurakCard('9H')])
        self.process.stdin.write.assert_called_once_with('give_more 7H\n')
        self.assertTrue(self.process.stdout.readline.called)

    def test_give_more_returns_none_if_no_output_given(self):
        self.process.stdout.readline.return_value = ''

        results = self.wrapper.give_more([DurakCard('7H')])

        self.assertTrue(results is None)
        self.process.stdin.write.assert_called_once_with('give_more 7H\n')
        self.assertTrue(self.process.stdout.readline.called)

    def test_give_more_raises_exception_if_cant_convert_output_to_cards(self):
        self.process.stdout.readline.return_value = 'error'
        with self.assertRaises(EngineWrapperException):
            self.wrapper.give_more([DurakCard('7H')])
