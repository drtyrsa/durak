# -*- coding: utf-8 -*-
from collections import namedtuple
from itertools import product, groupby


DurakCardTuple = namedtuple('DurakCardTuple', ['numeric_value', 'suit'])


class DurakCard(DurakCardTuple):

    VALUES = ('6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A')
    SUITS = ('H', 'S', 'D', 'C')

    _INSTANCE_REGISTRY = {}

    def __new__(cls, *args, **kwargs):
        value, suit = cls._parse_suit_and_value(*args, **kwargs)
        if (value, suit) in cls._INSTANCE_REGISTRY:
            return cls._INSTANCE_REGISTRY[(value, suit)]

        instance = super(DurakCard, cls).__new__(cls, value, suit)
        cls._INSTANCE_REGISTRY[(value, suit)] = instance
        return instance

    @classmethod
    def _parse_suit_and_value(cls, *args, **kwargs):
        # input value can be string like '7H'
        if len(args) == 1 and not kwargs:
            string = str(args[0]).strip()
            if len(string) != 2:
                raise ValueError('Input string should be 2 chars long')

            value, suit = string

        # or it can be two args like ('7', 'H')
        elif len(args) == 2 and not kwargs:
            value, suit = args

        # or it can be two kwargs like (value='7', suit='H')
        elif not args and kwargs:
            if 'suit' not in kwargs or 'value' not in kwargs:
                raise ValueError('Invalid arguments')
            value = kwargs['value']
            suit = kwargs['suit']
        else:
            raise ValueError('Invalid arguments')

        if suit.upper() not in cls.SUITS:
            raise ValueError('Invalid suit')

        try:
            value = cls.VALUES.index(value.upper())
        except ValueError:
            raise ValueError('Invalid value')

        return value, suit

    @classmethod
    def all(cls):
        return {cls(*args) for args in product(cls.VALUES, cls.SUITS)}

    @property
    def value(self):
        return self.VALUES[self.numeric_value]

    def __str__(self):
        return '%s%s' % (self.value, self.suit)

    __repr__ = __str__
    __unicode__ = __str__

    def __hash__(self):
        return hash(str(self))

    def __cmp__(self, other):
        if not isinstance(other, type(self)):
            raise ValueError(
                u'Can not compare DurakCard and %s instances' % type(other)
            )

        value_diff = self.numeric_value - other.numeric_value
        if value_diff != 0:
            return value_diff

        if self.suit == other.suit:
            return 0
        elif self.suit > other.suit:
            return 1
        else:
            return -1


class CardSet(set):

    def __init__(self, cards, trump):
        super(CardSet, self).__init__()
        self._trump = DurakCard(trump)

        self.update(map(DurakCard, cards))

    def cards_that_can_beat(self, card, including_trumps=True):
        card = DurakCard(card)

        if self._is_trump(card) and not including_trumps:
            return []

        results = [
            x for x in self.sorted_cards() if x.suit == card.suit and x > card
        ]
        if not self._is_trump(card) and including_trumps:
            results.extend(sorted(self.trumps()))

        return results

    def cards_that_can_be_added_to(self, cards, including_trumps=True):
        if not cards:
            return self.sorted_cards()

        values = {DurakCard(x).value for x in cards}
        results = [x for x in self.sorted_cards() if x.value in values]
        if not including_trumps:
            results = [x for x in results if not self._is_trump(x)]
        return results

    def card_groups(self, including_trumps=True):
        results = []

        if including_trumps:
            cards = self
        else:
            cards = self.not_trumps()

        key_func = lambda x: x.numeric_value
        sorted_cards = sorted(cards, key=key_func)
        for _, group in groupby(sorted_cards, key_func):
            group = set(group)
            if len(group) > 1:
                results.append(group)

        return results

    def _is_trump(self, card):
        card = DurakCard(card)
        return (card.suit == self._trump.suit)

    def trumps(self):
        return {x for x in self if self._is_trump(x)}

    def not_trumps(self):
        return {x for x in self if not self._is_trump(x)}

    def sorted_cards(self):
        results = list(sorted(self.not_trumps()))
        results.extend(sorted(self.trumps()))
        return results

    def lowest_trump(self):
        trumps = list(sorted(self.trumps()))
        if not trumps:
            return None
        return trumps[0]
