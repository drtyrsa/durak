# -*- coding: utf-8 -*-
import json
import sys


class BaseEngine(object):

    def init(self, trump):
        raise NotImplementedError

    def deal(self, cards, gamedata):
        raise NotImplementedError

    def move(self, cards, gamedata):
        raise NotImplementedError

    def respond(self, cards, gamedata):
        raise NotImplementedError

    def give_more(self, cards, gamedata):
        raise NotImplementedError

    def run(self):
        while True:
            line = sys.stdin.readline().strip()
            command_name, args, gamedata = self._parse_line(line)

            if command_name == 'init':
                output = self.init(args[0])
            elif command_name == 'deal':
                output = self.deal(args, gamedata=gamedata)
            elif command_name == 'move':
                output = self.move(args, gamedata=gamedata)
            elif command_name == 'respond':
                output = self.respond(args, gamedata=gamedata)
            elif command_name == 'give_more':
                output = self.give_more(args, gamedata=gamedata)
            elif command_name == 'game_end':
                return
            else:
                output = u'Error: Unknown command "%s"' % command_name

            self._output(output)

            if hasattr(self, 'only_one_iteration'):  # for unit testing
                break

    @staticmethod
    def _output(data):
        sys.stdout.write(str(data) + '\n')
        sys.stdout.flush()

    @staticmethod
    def _parse_line(line):
        if '##' in line:
            command, gamedata = line.split('##', 1)
            gamedata = json.loads(gamedata)
        else:
            command = line
            gamedata = {}

        try:
            command_name, args = command.split(None, 1)
            args = args.split()
        except ValueError:
            command_name = command
            args = []

        return command_name.strip(), args, gamedata
