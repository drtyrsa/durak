#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Durak Autoplay

Usage:
  durak-autoplay <path_to_engine1> <path_to_engine2> [--games-number=<count>] [--log-file=<path_to_file>] [--debug]
  durak-autoplay (-h | --help)
  durak-autoplay --version

Options:
  -h --help                  Show this help.
  --version                  Show version.
  --games-number=<count>     Number of games to play [default: 100].
  --log-file=<path_to_file>  Path to save games log file.
  --debug                    Print debug output.

"""
from collections import Counter
import logging
import os.path
import sys

from docopt import docopt

from durak.controller import GameController
from durak.engine.wrapper import EngineWrapper


ENGINE1 = 1
ENGINE2 = 2
DRAW = 3


def _play_game(engine1_path, engine2_path, log_filename=''):
    engine1 = EngineWrapper(engine1_path)
    engine2 = EngineWrapper(engine2_path)
    controller = GameController(
        player1_name=engine1_path,
        player2_name=engine2_path,
        log_filename=log_filename,
    )
    new_game_data = controller.start_new_game()

    engine1.init(new_game_data['trump'])
    engine2.init(new_game_data['trump'])

    engine1.deal(
        new_game_data['player1_cards'],
        controller.get_game_data_for(controller.PLAYER1)
    )
    engine2.deal(
        new_game_data['player2_cards'],
        controller.get_game_data_for(controller.PLAYER2)
    )

    while True:
        if controller.state == controller.States.MOVING:
            if controller.is_player1_to_move():
                engine_to_move = engine1
            else:
                engine_to_move = engine2

            card = engine_to_move.move(
                controller.on_table,
                controller.get_game_data_for(controller.MOVER)
            )
            controller.register_move(card)

        elif controller.state == controller.States.RESPONDING:
            if controller.is_player1_to_move():
                engine_to_respond = engine2
            else:
                engine_to_respond = engine1

            card = engine_to_respond.respond(
                controller.on_table,
                controller.get_game_data_for(controller.RESPONDER)
            )
            controller.register_response(card)

        elif controller.state == controller.States.GIVING_MORE:
            if controller.is_player1_to_move():
                engine_to_give_more = engine1
            else:
                engine_to_give_more = engine2

            cards = engine_to_give_more.give_more(
                controller.on_table,
                controller.get_game_data_for(controller.MOVER)
            )
            controller.register_give_more(cards)

        elif controller.state == controller.States.DEALING:
            deal_data = controller.deal()
            engine1.deal(
                deal_data['player1_cards'],
                controller.get_game_data_for(controller.PLAYER1)
            )
            engine2.deal(
                deal_data['player2_cards'],
                controller.get_game_data_for(controller.PLAYER2)
            )

        if controller.is_game_over():
            break

    engine1.game_end()
    engine2.game_end()

    if controller.winner == controller.PLAYER1:
        return ENGINE1
    elif controller.winner == controller.PLAYER2:
        return ENGINE2
    else:
        return DRAW


def _do_autoplay(engine1_path, engine2_path, games_number, log_filename=''):
    counter = Counter()
    for i in xrange(games_number):
        sys.stdout.write('\r%d of %d' % (i + 1, games_number))
        sys.stdout.flush()
        counter[_play_game(engine1_path, engine2_path, log_filename)] += 1

    sys.stdout.write('\n')
    sys.stdout.write(
        u'Engine1 (%s) wins:\t%d\n' % (engine1_path, counter[ENGINE1])
    )
    sys.stdout.write(
        u'Engine2 (%s) wins:\t%d\n' % (engine2_path, counter[ENGINE2])
    )
    sys.stdout.write(u'Draws:\t%d\n' % counter[DRAW])


def main():
    arguments = docopt(__doc__, version='Durak Autoplay v0.1')

    if arguments['--debug']:
        logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

    _do_autoplay(
        arguments['<path_to_engine1>'],
        arguments['<path_to_engine2>'],
        int(arguments['--games-number']),
        os.path.expanduser(arguments.get('--log-file', '')),
    )


if __name__ == '__main__':
    main()
