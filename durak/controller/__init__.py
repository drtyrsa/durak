# -*- coding: utf-8 -*-
import random

from durak.utils.cards import DurakCard, CardSet
from durak.controller import exceptions as exes


class Player(object):

    def __init__(self):
        self.cards = None


class Table(list):

    def __init__(self, *args, **kwargs):
        super(Table, self).__init__(*args, **kwargs)
        self.given_more = set()

    def give_more(self, cards):
        self.given_more.update(cards)

    def clear(self):
        self[:] = []
        self.given_more = set()


class GameController(object):

    MOVER = 'mover'
    RESPONDER = 'responder'
    PLAYER1 = 'player1'
    PLAYER2 = 'player2'

    class States:
        DEALING = 'dealing'
        MOVING = 'moving'
        RESPONDING = 'responding'
        GIVING_MORE = 'giving_more'

    def __init__(self):
        self._player1 = Player()
        self._player2 = Player()
        self._winner = None
        self._state = None

    def start_new_game(self, ignore_winner=True):
        self._deck = list(DurakCard.all())
        random.shuffle(self._deck)
        self._trump = self._deck[-1]

        self._player1.cards = CardSet(cards=self._deck[:6], trump=self._trump)
        self._player2.cards = CardSet(
            cards=self._deck[6:12], trump=self._trump
        )
        self._deck = self._deck[12:]

        self._first_discard_completed = False

        if not ignore_winner and self._winner is not None:
            self._to_move = self._winner
        else:
            self._to_move = self._get_first_to_move_by_trump()

        self._winner = None
        self._discarded = []
        self._on_table = Table()

        self._state = self.States.MOVING
        self._no_response = False

        return {
            'player1_cards': CardSet(self._player1.cards, trump=self._trump),
            'player2_cards': CardSet(self._player2.cards, trump=self._trump),
            'trump': DurakCard(self._trump),
        }

    def _get_first_to_move_by_trump(self):
        lowest_trump1 = self._player1.cards.lowest_trump()
        lowest_trump2 = self._player2.cards.lowest_trump()

        if lowest_trump1 is not None and lowest_trump2 is not None:
            if lowest_trump1 < lowest_trump2:
                return self._player1
            else:
                return self._player2
        elif lowest_trump1 is None and lowest_trump2 is not None:
            return self._player2
        elif lowest_trump1 is not None and lowest_trump2 is None:
            return self._player1
        else:
            return random.choice([self._player1, self._player2])

    def _get_game_data_for(self, player):
        return {
            'trump': str(DurakCard(self._trump)),
            'deck_count': self.deck_count,
            'enemy_count': len(self._get_enemy_of(player).cards),
            'on_table': map(str, self._on_table),
            'discarded': map(str, self._discarded),
        }

    def get_game_data_for(self, player):
        assert player in (
            self.MOVER, self.RESPONDER, self.PLAYER1, self.PLAYER2
        )

        if player == self.MOVER:
            return self._get_game_data_for(self._to_move)
        elif player == self.RESPONDER:
            return self._get_game_data_for(self._to_respond)
        elif player == self.PLAYER1:
            return self._get_game_data_for(self._player1)
        elif player == self.PLAYER2:
            return self._get_game_data_for(self._player2)

    def _get_enemy_of(self, player):
        assert player in (self._player1, self._player2)

        if player is self._player1:
            return self._player2
        else:
            return self._player1

    @property
    def _to_respond(self):
        return self._get_enemy_of(self._to_move)

    def is_player1_to_move(self):
        return (self._to_move is self._player1)

    def register_move(self, card):
        if self._state != self.States.MOVING:
            raise exes.InvalidAction(
                expected=self._state, got=self.States.MOVING
            )

        if card is None:
            if not self._on_table:
                raise exes.CardIsExpected
            self._state = self.States.DEALING
            return

        card = DurakCard(card)
        if card not in self._to_move.cards:
            raise exes.PlayerDoesNotHaveCard(card)

        if card not in (self._to_move.cards
                            .cards_that_can_be_added_to(self._on_table)):
            raise exes.InvalidCard(
                'Can not move with card %s (on table: %s)' % (
                    card, self._on_table
                )
            )

        self._to_move.cards.remove(card)
        self._on_table.append(card)
        self._state = self.States.RESPONDING

        self._check_for_game_over()

    def register_response(self, card):
        if self._state != self.States.RESPONDING:
            raise exes.InvalidAction(
                expected=self._state, got=self.States.RESPONDING
            )

        if card is None:
            self._no_response = True
            if self._to_move.cards:
                self._state = self.States.GIVING_MORE
            else:
                self._state = self.States.DEALING
            return

        card = DurakCard(card)
        card_to_beat = self._on_table[-1]

        if card not in self._to_respond.cards:
            raise exes.PlayerDoesNotHaveCard(card)

        if card not in (self._to_respond.cards
                            .cards_that_can_beat(card_to_beat)):
            raise exes.InvalidCard(
                'Card %s can not beat card %s (trump is %s)' % (
                    card, card_to_beat, self._trump
                )
            )

        self._to_respond.cards.remove(card)
        self._on_table.append(card)

        if not (self._to_respond.cards and self._to_move.cards):
            self._state = self.States.DEALING
        elif not self._first_discard_completed and len(self._on_table) >= 10:
            self._state = self.States.DEALING
        else:
            self._state = self.States.MOVING

        self._check_for_game_over()

    def register_give_more(self, cards):
        assert self._no_response

        if self._state != self.States.GIVING_MORE:
            raise exes.InvalidAction(
                expected=self._state, got=self.States.GIVING_MORE
            )

        if not cards:
            self._state = self.States.DEALING
            return

        cards = set(map(DurakCard, cards))
        invalid_cards = cards - self._to_move.cards
        if invalid_cards:
            raise exes.PlayerDoesNotHaveCard(*invalid_cards)

        allowed_cards = self._to_move.cards.cards_that_can_be_added_to(
            self._on_table
        )
        invalid_cards = cards - set(allowed_cards)
        if invalid_cards:
            raise exes.InvalidCard(
                'Can not give more cards %s (on table: %s)' % (
                    invalid_cards, self._on_table
                )
            )

        self._to_move.cards.difference_update(cards)
        self._on_table.give_more(cards)

        self._state = self.States.DEALING

        self._check_for_game_over()

    def deal(self):
        if self._state != self.States.DEALING:
            raise exes.InvalidAction(
                expected=self._state, got=self.States.DEALING
            )

        if self._no_response:
            self._to_respond.cards.update(self._on_table)
            self._to_respond.cards.update(self._on_table.given_more)
            self._no_response = False
        else:
            self._to_move = self._to_respond
            self._discarded.extend(self._on_table)
            if not self._first_discard_completed:
                self._first_discard_completed = True

        self._on_table.clear()
        self._state = self.States.MOVING

        for player in (self._to_respond, self._to_move):
            if not self._deck:
                break

            cards_needed = 6 - len(player.cards)
            if cards_needed > 0:
                player.cards.update(self._deck[:cards_needed])
                self._deck = self._deck[cards_needed:]

        self._check_for_game_over()

        return {
            'player1_cards': CardSet(self._player1.cards, trump=self._trump),
            'player2_cards': CardSet(self._player2.cards, trump=self._trump),
        }

    def is_game_over(self):
        return (self.state is None)

    def _check_for_game_over(self):
        if self._deck:
            return

        if self._player1.cards and self._player2.cards:
            return

        if self._state == self.States.RESPONDING:
            if not self._to_move.cards and len(self._to_respond.cards) == 1:
                can_beat = self._to_respond.cards.cards_that_can_beat(
                    self._on_table[-1]
                )
                if can_beat:
                    return

        if not (self._player1.cards or self._player2.cards):
            self._winner = None
        elif not self._player1.cards:
            self._winner = self._player1
        elif not self._player2.cards:
            self._winner = self._player2

        self._state = None

    @property
    def state(self):
        return self._state

    @property
    def on_table(self):
        return self._on_table[:]

    @property
    def winner(self):
        if self._winner == self._player1:
            return self.PLAYER1
        elif self._winner == self._player2:
            return self.PLAYER2
        return None

    @property
    def to_move(self):
        if self._to_move == self._player1:
            return self.PLAYER1

        return self.PLAYER2

    @property
    def deck_count(self):
        return len(self._deck)
