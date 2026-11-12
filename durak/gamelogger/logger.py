# -*- coding: utf-8 -*-
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4


def new_log_filename(directory):
    directory = Path(directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    name = datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-' + uuid4().hex[:8] + '.log'
    return str((directory / name).resolve())


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
        self._log['deck'] = list(map(str, deck))
        self._log['opened_trump'] = str(opened_trump)
        self._log['started_at'] = datetime.now().isoformat()

    def log_after_game(self, winner, luck=None):
        self._log['result'] = self._get_result(winner)
        self._log['ended_at'] = datetime.now().isoformat()
        if luck is not None:
            self._log['luck'] = luck

    def log_before_move(self, player1_cards, player2_cards, to_move,
                        deck_count):
        assert to_move in (self.PLAYER1, self.PLAYER2)
        assert deck_count >= 0

        move = {}
        move['player1_cards'] = list(map(str, player1_cards))
        move['player2_cards'] = list(map(str, player2_cards))
        move['to_move'] = to_move
        move['deck_count'] = deck_count
        self._log['moves'].append(move)

    def log_after_move(self, moves_and_responds, given_more):
        move = self._log['moves'][-1]
        move['moves_and_responds'] = list(map(str, moves_and_responds))
        move['given_more'] = list(map(str, given_more))

    def log_action(self, player, phase, cards, hand, on_table, gamedata, analysis=None):
        """Optional per-action data; the existing wx replay fields stay intact."""
        action = {'player': player, 'phase': phase, 'cards': list(map(str, cards)),
                  'hand': list(map(str, sorted(hand))), 'on_table': list(map(str, on_table)),
                  'gamedata': gamedata, 'at': datetime.now().isoformat()}
        if analysis is not None:
            action['analysis'] = analysis
        self._log['moves'][-1].setdefault('actions', []).append(action)

    def log_interrupted(self, reason):
        self._log['status'] = 'interrupted'
        self._log['interruption_reason'] = reason
        self._log['ended_at'] = datetime.now().isoformat()

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
            self._log.get('result', self._log.get('status', 'in progress'))
        )

    def write_to_file(self, filename, overwrite=False):
        if overwrite:
            open_mode = 'w'
        else:
            open_mode = 'a'

        json_str = json.dumps(self._log)

        with open(filename, open_mode) as f:
            f.write('####%s####\n%s\n' % (self._log_title, json_str))

    def write_snapshot(self, filename):
        """Replace a live replay atomically so readers never see half-written JSON."""
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=Path(filename).parent, delete=False) as stream:
                temporary = stream.name
                stream.write('####%s####\n%s\n' % (self._log_title, json.dumps(self._log)))
            os.replace(temporary, filename)
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
