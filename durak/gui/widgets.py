# -*- coding: utf-8 -*-
from collections import OrderedDict

import wx

from durak.gui.images import card_image_manager


class CardButton(wx.BitmapButton):
    def __init__(self, *args, **kwargs):
        card = kwargs.pop('card')
        kwargs.update(dict(
            bitmap=card_image_manager.get_image(card),
            style=wx.NO_BORDER
        ))
        super(CardButton, self).__init__(*args, **kwargs)
        self._card = card

    @property
    def card(self):
        return self._card

    @card.setter
    def card(self, some_card):
        self._card = some_card
        self.SetBitmapLabel(card_image_manager.get_image(some_card))


class Card(wx.StaticBitmap):
    def __init__(self, *args, **kwargs):
        card = kwargs.pop('card')
        kwargs.update(dict(
            bitmap=card_image_manager.get_image(card),
            style=wx.NO_BORDER
        ))
        super(Card, self).__init__(*args, **kwargs)


class HiddenCard(wx.StaticBitmap):
    def __init__(self, *args, **kwargs):
        kwargs.update(dict(
            bitmap=card_image_manager.get_hidden_card_image(),
            style=wx.NO_BORDER
        ))
        super(HiddenCard, self).__init__(*args, **kwargs)


class CardSizer(wx.BoxSizer):
    def __init__(self, *args, **kwargs):
        self._parent = kwargs.pop('parent')
        self._on_click = kwargs.pop('on_click')
        super(CardSizer, self).__init__(*args, **kwargs)
        self._trump = None
        self._buttons_dict = {}

    def add_card(self, card, do_layout=False):
        card_button = CardButton(parent=self._parent, card=card)
        card_button.Bind(wx.EVT_BUTTON, self._on_click)

        self._insert_button(card_button)

        self._buttons_dict[card] = card_button
        card_button.Show()
        if do_layout:
            self.Layout()

    def _insert_button(self, new_button):
        inserted = False
        for index, button in enumerate(self.GetChildren()):
            card = button.GetWindow().card
            if card.is_less_than(new_button.card, trump=self._trump):
                self.Insert(index, new_button)
                inserted = True
                break

        if not inserted:
            self.Add(new_button)

    @property
    def trump(self):
        return self._trump

    @trump.setter
    def trump(self, trump):
        self._trump = trump

    def remove_card(self, card, do_layout=False):
        card_button = self._buttons_dict.pop(card)
        self.Detach(card_button)
        card_button.Destroy()

        if do_layout:
            self.Layout()

    def remove_all(self, do_layout=False):
        self.Clear(deleteWindows=True)
        self._buttons_dict = {}

        if do_layout:
            self.Layout()

    def enable_all(self):
        for card_button in self._buttons_dict.itervalues():
            card_button.Enable()

    def set_enabled_cards(self, cards):
        for card, card_button in self._buttons_dict.iteritems():
            if card in cards:
                card_button.Enable()
            else:
                card_button.Disable()


class EnemyCardSizer(wx.BoxSizer):
    BORDER_SIZE = 6

    def __init__(self, *args, **kwargs):
        self._parent = kwargs.pop('parent')
        super(EnemyCardSizer, self).__init__(*args, **kwargs)
        self._cards = []

    def set_count(self, count):
        assert count >= 0

        current_count = len(self._cards)

        if count == current_count:
            return

        elif count < current_count:
            for _ in xrange(count, current_count):
                card = self._cards.pop()
                self.Detach(card)
                card.Destroy()

        elif count > current_count:
            cards = [
                HiddenCard(parent=self._parent)
                for _ in xrange(current_count, count)
            ]
            self.AddMany((card, 0, wx.ALL, self.BORDER_SIZE) for card in cards)
            self._cards.extend(cards)

        self.Layout()

    def decrement(self):
        assert self._cards

        self.set_count(len(self._cards) - 1)


class TablePanel(wx.Panel):
    CARD_PAIR_WIDTH = 55
    UPPER_CARD_Y_OFFSET = 10
    UPPER_CARD_X_OFFSET = 20
    GIVEN_MORE_OFFSET = 95
    PADDING_LEFT = 10

    def __init__(self, *args, **kwargs):
        super(TablePanel, self).__init__(*args, **kwargs)
        self._cards = OrderedDict()
        self._give_more_mode = False

        self.SetSizeHints(640, 150)

    def _add_card(self, card, position):
        card_img = Card(parent=self, card=card, pos=position)
        self._cards[card] = card_img
        card_img.Show()

    def move(self, card):
        assert not self._give_more_mode
        assert not self._is_odd

        position = (
            self.CARD_PAIR_WIDTH * (len(self._cards)) + self.PADDING_LEFT,
            self.UPPER_CARD_Y_OFFSET
        )
        self._add_card(card, position)

    def respond(self, card):
        assert not self._give_more_mode
        assert self._is_odd

        last_card_img = self._cards.values()[-1]
        position = (
            last_card_img.GetPosition() +
            wx.Point(self.UPPER_CARD_X_OFFSET, -self.UPPER_CARD_Y_OFFSET)
        )
        self._add_card(card, position)

    def give_more(self, card):
        assert self._give_more_mode or self._is_odd

        last_card_img = self._cards.values()[-1]
        x = last_card_img.GetPosition()[0] + self.GIVEN_MORE_OFFSET
        position = (x, self.UPPER_CARD_Y_OFFSET)

        self._add_card(card, position)
        self._give_more_mode = True

    def remove_all(self):
        for card in self._cards.itervalues():
            card.Destroy()

        self._cards = OrderedDict()
        self._give_more_mode = False

    @property
    def cards(self):
        return self._cards.keys()

    @property
    def _is_odd(self):
        return len(self._cards) % 2


class DeckPanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        super(DeckPanel, self).__init__(*args, **kwargs)
        self._opened_trump = wx.StaticBitmap(parent=self, pos=(0, 12))
        self._deck_top = HiddenCard(parent=self, pos=(50, 0))
        self._card_count = wx.StaticText(parent=self, pos=(70, 100))

        self._opened_trump.Hide()
        self._deck_top.Hide()

        self._trump_card = None

    def set_opened_trump(self, card):
        img = card_image_manager.get_image(card).ConvertToImage()
        img = img.Rotate90(clockwise=False)
        self._opened_trump.SetBitmap(img.ConvertToBitmap())

        self._trump_card = card

    def set_card_count(self, count):
        assert count >= 0

        self._card_count.SetLabel(str(count))

        self._deck_top.Show(count > 1)
        self._opened_trump.Show(count > 0)

        if count == 0:
            self._card_count.SetLabel(u'Козырь - %s' % str(self._trump_card))
