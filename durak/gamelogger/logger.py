# -*- coding: utf-8 -*-
from datetime import datetime
import json


class GameLogger(object):
    PLAYER1 = 'player1'
    PLAYER2 = 'player2'

    def __init__(self):
        self.reset()

    def reset(self):
        self._log = {}
        self._log['moves'] = []

    def log_before_game(self, player1_name, player2_name, deck, opened_trump):
        self._log['player1_name'] = player1_name
        self._log['player2_name'] = player2_name
        self._log['deck'] = map(str, deck)
        self._log['opened_trump'] = str(opened_trump)
        self._log['started_at'] = datetime.now().isoformat()

    def log_after_game(self, winner):
        self._log['result'] = self._get_result(winner)
        self._log['ended_at'] = datetime.now().isoformat()

    def log_before_move(self, player1_cards, player2_cards, to_move,
                        deck_count):
        assert to_move in (self.PLAYER1, self.PLAYER2)
        assert deck_count >= 0

        move = {}
        move['player1_cards'] = map(str, player1_cards)
        move['player2_cards'] = map(str, player2_cards)
        move['to_move'] = to_move
        move['deck_count'] = deck_count
        self._log['moves'].append(move)

    def log_after_move(self, moves_and_responds, given_more):
        move = self._log['moves'][-1]
        move['moves_and_responds'] = map(str, moves_and_responds)
        move['given_more'] = map(str, given_more)

    @classmethod
    def _get_result(cls, winner):
        assert winner in (cls.PLAYER1, cls.PLAYER2, None)

        if winner == cls.PLAYER1:
            return '1-0'
        elif winner == cls.PLAYER2:
            return '0-1'
        return 's-s'

    @property
    def _log_title(self):
        return u'%s, %s - %s (%s)' % (
            self._log['started_at'].split('.')[0],
            self._log['player1_name'],
            self._log['player2_name'],
            self._log['result']
        )

    def write_to_file(self, filename, overwrite=False):
        if overwrite:
            open_mode = 'w'
        else:
            open_mode = 'a'

        json_str = json.dumps(self._log)

        with open(filename, open_mode) as f:
            f.write('####%s####\n%s\n' % (self._log_title, json_str))
