#!/usr/bin/env python
# -*- coding: utf-8 -*-
from durak.engine.base import BaseEngine
from durak.utils.cards import CardSet


class DummyEngine(BaseEngine):

    def init(self, trump):
        self._cards = CardSet([], trump)
        return 'ok'

    def deal(self, cards, gamedata):
        self._cards.update(cards)
        return 'ok'

    def move(self, on_table, gamedata):
        assert self._cards

        if not on_table:
            cards = self._cards.cards_that_can_be_added_to(on_table)
        else:
            cards = self._cards.cards_that_can_be_added_to(
                on_table, including_trumps=False
            )
        if cards:
            result = cards[0]
            self._cards.remove(result)
            return result
        return ''

    def respond(self, on_table, gamedata):
        assert self._cards

        cards = self._cards.cards_that_can_beat(on_table[-1])
        if cards:
            result = cards[0]
            self._cards.remove(result)
            return result
        return ''

    def give_more(self, on_table, gamedata):
        assert self._cards

        max_count = gamedata['enemy_count'] - 1
        cards = self._cards.cards_that_can_be_added_to(
            on_table, including_trumps=False
        )[:max_count]
        self._cards.difference_update(cards)
        return ' '.join(map(str, cards))


def main():
    DummyEngine().run()


if __name__ == '__main__':
    main()
