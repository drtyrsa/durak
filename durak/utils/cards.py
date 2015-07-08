# -*- coding: utf-8 -*-
from collections import namedtuple
from itertools import product, groupby


DurakCardTuple = namedtuple('DurakCardTuple', ['numeric_rank', 'suit'])


class DurakCard(DurakCardTuple):

    RANKS = ('6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A')
    SUITS = ('C', 'D', 'H', 'S')

    _INSTANCE_REGISTRY = {}

    def __new__(cls, *args, **kwargs):
        rank, suit = cls._parse_suit_and_rank(*args, **kwargs)
        if (rank, suit) in cls._INSTANCE_REGISTRY:
            return cls._INSTANCE_REGISTRY[(rank, suit)]

        instance = super(DurakCard, cls).__new__(cls, rank, suit)
        cls._INSTANCE_REGISTRY[(rank, suit)] = instance
        return instance

    @classmethod
    def _parse_suit_and_rank(cls, *args, **kwargs):
        # input value can be string like '7H'
        if len(args) == 1 and not kwargs:
            string = str(args[0]).strip()
            if len(string) != 2:
                raise ValueError('Input string should be 2 chars long')

            rank, suit = string

        # or it can be two args like ('7', 'H')
        elif len(args) == 2 and not kwargs:
            rank, suit = args

        # or it can be two kwargs like (rank='7', suit='H')
        elif not args and kwargs:
            if 'suit' not in kwargs or 'rank' not in kwargs:
                raise ValueError('Invalid arguments')
            rank = kwargs['rank']
            suit = kwargs['suit']
        else:
            raise ValueError('Invalid arguments')

        if suit.upper() not in cls.SUITS:
            raise ValueError('Invalid suit')

        try:
            rank = cls.RANKS.index(rank.upper())
        except ValueError:
            raise ValueError('Invalid rank')

        return rank, suit

    @classmethod
    def all(cls):
        return {cls(*args) for args in product(cls.RANKS, cls.SUITS)}

    @property
    def rank(self):
        return self.RANKS[self.numeric_rank]

    @property
    def numeric_suit(self):
        return self.SUITS.index(self.suit)

    def is_less_than(self, other, trump=None):
        if not isinstance(other, type(self)):
            raise ValueError(
                u'Can not compare DurakCard and %s instances' % type(other)
            )

        if trump is not None:
            if not isinstance(trump, type(self)):
                raise ValueError(
                    u'Trump should be DurakCard instance, not %s' % type(trump)
                )

            if (self.suit == trump.suit and other.suit != trump.suit):
                return False

            if (self.suit != trump.suit and other.suit == trump.suit):
                return True

        return (self < other)

    def __str__(self):
        return '%s%s' % (self.rank, self.suit)

    __repr__ = __str__
    __unicode__ = __str__

    def __hash__(self):
        return hash(str(self))

    def __cmp__(self, other):
        if not isinstance(other, type(self)):
            raise ValueError(
                u'Can not compare DurakCard and %s instances' % type(other)
            )

        rank_diff = self.numeric_rank - other.numeric_rank
        if rank_diff != 0:
            return rank_diff

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

        ranks = {DurakCard(x).rank for x in cards}
        results = [x for x in self.sorted_cards() if x.rank in ranks]
        if not including_trumps:
            results = [x for x in results if not self._is_trump(x)]
        return results

    def card_groups(self, including_trumps=True):
        results = []

        if including_trumps:
            cards = self
        else:
            cards = self.not_trumps()

        key_func = lambda x: x.numeric_rank
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

    def update(self, iterable):
        return super(CardSet, self).update(map(DurakCard, iterable))
