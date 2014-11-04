# -*- coding: utf-8 -*-
import json

from durak.utils.cards import CardSet, DurakCard


class InvalidLogFormat(ValueError):
    pass


class LogViewer(object):
    PLAYER1 = 'player1'
    PLAYER2 = 'player2'

    MOVE = 'move'
    RESPOND = 'respond'
    NEW_MOVE = 'new_move'
    GIVE_MORE = 'give_more'

    INITIAL_CURRENT_MOVE = 0
    INITIAL_CURRENT_TABLE_INDEX = -1

    def __init__(self, filename):
        self._current_game = None
        self._current_move = self.INITIAL_CURRENT_MOVE
        self._current_table_index = self.INITIAL_CURRENT_TABLE_INDEX

        self._filename = filename
        self._game_index = []
        self._fill_game_index()

    def iterindex(self):
        return iter(self._game_index)

    def load_game(self, index):
        self._current_game = None

        file_pos = self._game_index[index]['start_offset']
        size_to_read = -1
        if index != len(self._game_index) - 1:
            size_to_read = (
                self._game_index[index + 1]['prev_end_offset'] - file_pos
            )
        try:
            with open(self._filename, 'r') as f:
                f.seek(file_pos)
                json_str = f.read(size_to_read)
                try:
                    self._current_game = json.loads(json_str)
                except ValueError:
                    raise InvalidLogFormat(u'Hеверный формат файла')
        except IOError:
            raise InvalidLogFormat(u'Hе могу прочитать файл')

    @property
    def has_game_loaded(self):
        return bool(self._current_game)

    def get_next(self):
        assert self._current_game
        assert self.has_next

        result = {}
        cur_move = self._current_game['moves'][self._current_move]

        if self._current_table_index == self.INITIAL_CURRENT_TABLE_INDEX:
            result = self._get_new_move(cur_move)
        else:
            mr_len = len(cur_move['moves_and_responds'])
            if self._current_table_index < mr_len:
                result['card'] = (
                    DurakCard(
                        cur_move['moves_and_responds']
                                [self._current_table_index]
                    )
                )
                if self._current_table_index % 2:
                    to_move = self._get_opposite_player(cur_move['to_move'])
                    event_type = self.RESPOND
                else:
                    to_move = cur_move['to_move']
                    event_type = self.MOVE
                result['to_move'] = to_move
                result['event_type'] = event_type
            else:
                result['event_type'] = self.GIVE_MORE
                result['card'] = DurakCard(cur_move['given_more'][
                    self._current_table_index - mr_len
                ])
                result['to_move'] = cur_move['to_move']

        self._increment()
        return result

    @property
    def has_next(self):
        if self._current_move < len(self._current_game['moves']) - 1:
            return True

        if self._current_move >= len(self._current_game['moves']):
            return False

        cur_move = self._current_game['moves'][self._current_move]
        if self._current_table_index < (
                len(cur_move['moves_and_responds']) +
                len(cur_move['given_more'])):
            return True

        return False

    def get_prev(self):
        assert self._current_game
        assert self.has_prev

        result = {}

        self._decrement()

        if self._current_table_index == self.INITIAL_CURRENT_TABLE_INDEX:
            cur_move = self._current_game['moves'][self._current_move - 1]
            result = self._get_new_move(cur_move)
        else:
            cur_move = self._current_game['moves'][self._current_move]
            mr_len = len(cur_move['moves_and_responds'])
            if self._current_table_index < mr_len:
                result['card'] = (
                    DurakCard(
                        cur_move['moves_and_responds']
                                [self._current_table_index]
                    )
                )
                if self._current_table_index % 2:
                    to_move = self._get_opposite_player(cur_move['to_move'])
                    event_type = self.RESPOND
                else:
                    to_move = cur_move['to_move']
                    event_type = self.MOVE
                result['to_move'] = to_move
                result['event_type'] = event_type
            else:
                result['event_type'] = self.GIVE_MORE
                result['card'] = DurakCard(cur_move['given_more'][
                    self._current_table_index - mr_len
                ])
                result['to_move'] = cur_move['to_move']

        return result

    @property
    def has_prev(self):
        return (
            self._current_move > self.INITIAL_CURRENT_MOVE or
            self._current_table_index > self.INITIAL_CURRENT_TABLE_INDEX + 1
        )

    def _get_new_move(self, log_move):
        result = {}
        result['event_type'] = self.NEW_MOVE
        result.update(log_move)
        for key in ('player1_cards', 'player2_cards'):
            result[key] = self._to_card_set(result[key])
        for key in ('moves_and_responds', 'given_more'):
            result[key] = map(DurakCard, result[key])

        return result

    @property
    def opened_trump(self):
        assert self._current_game

        return DurakCard(self._current_game['opened_trump'])

    def _increment(self):
        assert self._current_game

        if not self.has_next:
            return

        cur_move = self._current_game['moves'][self._current_move]

        if self._current_table_index < (
                len(cur_move['moves_and_responds']) +
                len(cur_move['given_more']) - 1):
            self._current_table_index += 1
        else:
            self._current_move += 1
            self._current_table_index = self.INITIAL_CURRENT_TABLE_INDEX

    def _decrement(self):
        assert self._current_game

        if not self.has_prev:
            return

        if self._current_table_index > self.INITIAL_CURRENT_TABLE_INDEX:
            self._current_table_index -= 1
        else:
            self._current_move -= 1
            cur_move = self._current_game['moves'][self._current_move]
            self._current_table_index = (
                len(cur_move['moves_and_responds']) +
                len(cur_move['given_more']) - 1
            )

    def to_game_start(self):
        assert self._current_game

        self._current_move = self.INITIAL_CURRENT_MOVE
        self._current_table_index = self.INITIAL_CURRENT_TABLE_INDEX

    def to_game_end(self):
        assert self._current_game

        self._current_move = len(self._current_game['moves'])
        self._current_table_index = self.INITIAL_CURRENT_TABLE_INDEX + 1

    @property
    def player1_name(self):
        assert self._current_game

        return self._current_game['player1_name']

    @property
    def player2_name(self):
        assert self._current_game

        return self._current_game['player2_name']

    def _fill_game_index(self):
        self._game_index = []

        try:
            with open(self._filename, 'r') as f:
                while True:
                    line = f.readline()
                    if not line:
                        break

                    initial_len = len(line)
                    line = line.strip()
                    if not line.startswith('####') or not line.endswith('####'):
                        continue

                    game_index_item = {}
                    game_index_item['title'] = line.strip('#')
                    game_index_item['start_offset'] = f.tell()
                    game_index_item['prev_end_offset'] = (
                        game_index_item['start_offset'] - initial_len
                    )
                    self._game_index.append(game_index_item)
        except IOError:
            raise InvalidLogFormat(u'Не могу прочитать файл')

        if not self._game_index:
            raise InvalidLogFormat(u'В файле не найдено игр')

    def _get_opposite_player(self, player):
        assert player in (self.PLAYER1, self.PLAYER2)

        if player == self.PLAYER1:
            return self.PLAYER2

        return self.PLAYER1

    def _to_card_set(self, cards):
        return CardSet(cards, trump=self.opened_trump)
