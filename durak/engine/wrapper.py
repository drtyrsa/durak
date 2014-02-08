# -*- coding: utf-8 -*-
import logging
import json
import subprocess

from durak.utils.cards import DurakCard


logger = logging.getLogger(__name__)


class EngineWrapperException(Exception):
    pass


class EngineWrapper(object):

    def __init__(self, engine_path):
        self._process = subprocess.Popen(
            engine_path, stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )

    def init(self, trump):
        self._write_command('init', [trump])
        output = self._get_output()
        if output != 'ok':
            raise EngineWrapperException(
                'Init should return "ok", got %s instead' % output
            )

    def deal(self, cards, gamedata=None):
        self._write_command('deal', cards, gamedata)
        output = self._get_output()
        if output != 'ok':
            raise EngineWrapperException(
                'Deal should return "ok", got %s instead' % output
            )

    def move(self, on_table, gamedata=None):
        self._write_command('move', on_table, gamedata)
        output = self._get_output()
        if not output:
            return None

        try:
            card = DurakCard(output)
        except ValueError:
            raise EngineWrapperException(
                'Can not convert this result of Move to card: %s' % output
            )

        return card

    def respond(self, on_table, gamedata=None):
        self._write_command('respond', on_table, gamedata)
        output = self._get_output()
        if not output:
            return None

        try:
            card = DurakCard(output)
        except ValueError:
            raise EngineWrapperException(
                'Can not convert this result of Respond to card: %s' % output
            )

        return card

    def give_more(self, on_table, gamedata=None):
        self._write_command('give_more', on_table, gamedata)
        output = self._get_output()
        if not output:
            return None

        try:
            cards = map(DurakCard, output.split())
        except ValueError:
            raise EngineWrapperException(
                'Can not convert this result of Give_more to cards: %s' %
                output
            )

        return cards

    def game_end(self):
        self._write('game_end')
        self._process.kill()
        self._process = None

    def _write(self, line):
        logger.debug('sending: (' + str(id(self)) + '): %s' % line)
        self._process.stdin.write(line.strip() + '\n')

    def _write_command(self, command, cards, gamedata=None):
        line = command + ' ' + ' '.join(map(str, cards))
        if gamedata is not None:
            line += (' ## ' + json.dumps(gamedata))
        self._write(line.strip())

    def _get_output(self):
        result = self._process.stdout.readline().strip()
        logger.debug('receiving: (' + str(id(self)) + '): %s' % result)
        return result
