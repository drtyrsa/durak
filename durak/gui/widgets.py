# -*- coding: utf-8 -*-
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
