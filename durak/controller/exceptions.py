# -*- coding: utf-8 -*-


class GameControllerError(Exception):
    pass


class InvalidAction(GameControllerError):

    def __init__(self, expected, got):
        super(InvalidAction, self).__init__(
            '"%s" expected, got "%s" instead' % (expected, got)
        )


class CardIsExpected(GameControllerError):
    pass


class PlayerDoesNotHaveCard(GameControllerError):

    def __init__(self, *args):
        super(PlayerDoesNotHaveCard, self).__init__(
            'Player does not have these cards: %s' % str(args)
        )


class InvalidCard(GameControllerError):
    pass


class TooMuchGiveMoreCards(GameControllerError):

    def __init__(self, got_count, max_count):
        super(TooMuchGiveMoreCards, self).__init__(
            'Too much give more cards: %d (max is %d)' % (got_count, max_count)
        )
