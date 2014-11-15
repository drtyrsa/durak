# -*- coding: utf-8 -*-
from collections import OrderedDict

import wx

from durak.gui.images import card_image_manager
from durak.utils.cards import CardSet


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


class CardSizerMixin(object):
    def __init__(self, *args, **kwargs):
        self._parent = kwargs.pop('parent')
        self._on_click = kwargs.pop('on_click', None)
        super(CardSizerMixin, self).__init__(*args, **kwargs)
        self._trump = None
        self._buttons_dict = {}

    def add_card(self, card, do_layout=False):
        card_button = CardButton(parent=self._parent, card=card)
        if self._on_click is not None:
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
    def cards(self):
        return CardSet(self._buttons_dict.iterkeys(), self._trump)

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

    def disable_all(self):
        for card_button in self._buttons_dict.itervalues():
            card_button.Disable()

    def set_enabled_cards(self, cards):
        for card, card_button in self._buttons_dict.iteritems():
            if card in cards:
                card_button.Enable()
            else:
                card_button.Disable()


class CardSizer(CardSizerMixin, wx.BoxSizer):
    pass


class LabeledCardSizer(CardSizerMixin, wx.StaticBoxSizer):
    def __init__(self, *args, **kwargs):
        parent = kwargs['parent']
        self._staticbox = wx.StaticBox(parent)
        super(LabeledCardSizer, self).__init__(
            self._staticbox, *args, **kwargs
        )

    def set_label(self, text):
        return self._staticbox.SetLabel(text)


class EnemyCardSizer(wx.BoxSizer):
    BORDER_SIZE = 6

    def __init__(self, *args, **kwargs):
        self._parent = kwargs.pop('parent')
        super(EnemyCardSizer, self).__init__(*args, **kwargs)
        self._cards = []

    def set_count(self, count):
        assert count >= 0

        if count == self.count:
            return

        elif count < self.count:
            for _ in xrange(count, self.count):
                card = self._cards.pop()
                self.Detach(card)
                card.Destroy()

        elif count > self.count:
            cards = [
                HiddenCard(parent=self._parent)
                for _ in xrange(self.count, count)
            ]
            self.AddMany((card, 0, wx.ALL, self.BORDER_SIZE) for card in cards)
            self._cards.extend(cards)

        self.Layout()

    def decrement(self):
        assert self._cards

        self.set_count(len(self._cards) - 1)

    @property
    def count(self):
        return len(self._cards)


class TablePanel(wx.Panel):
    CARD_PAIR_WIDTH = 55
    UPPER_CARD_Y_OFFSET = 10
    UPPER_CARD_X_OFFSET = 20
    GIVEN_MORE_OFFSET = 95
    PADDING_LEFT = 10

    def __init__(self, *args, **kwargs):
        super(TablePanel, self).__init__(*args, **kwargs)
        self._cards = OrderedDict()
        self._given_more = []

        self.SetSizeHints(640, 150)

    def _add_card(self, card, position):
        card_img = Card(parent=self, card=card, pos=position)
        self._cards[card] = card_img
        card_img.Show()

    def move(self, card):
        assert not self._given_more
        assert not self._is_odd

        position = (
            self.CARD_PAIR_WIDTH * (len(self._cards)) + self.PADDING_LEFT,
            self.UPPER_CARD_Y_OFFSET
        )
        self._add_card(card, position)

    def respond(self, card):
        assert not self._given_more
        assert self._is_odd

        last_card_img = self._cards.values()[-1]
        position = (
            last_card_img.GetPosition() +
            wx.Point(self.UPPER_CARD_X_OFFSET, -self.UPPER_CARD_Y_OFFSET)
        )
        self._add_card(card, position)

    def give_more(self, card):
        assert self._given_more or self._is_odd

        last_card_img = self._cards.values()[-1]
        x = last_card_img.GetPosition()[0] + self.GIVEN_MORE_OFFSET
        position = (x, self.UPPER_CARD_Y_OFFSET)

        self._add_card(card, position)
        self._given_more.append(card)

    def remove_all(self):
        for card in self._cards.itervalues():
            card.Destroy()

        self._cards = OrderedDict()
        self._given_more = []

    def pop(self):
        if self._given_more:
            card = self._given_more.pop()
            card_img = self._cards.pop(card)
        else:
            card, card_img = self._cards.popitem(last=True)

        card_img.Destroy()
        return card

    @property
    def given_more(self):
        return self._given_more[:]

    @property
    def cards(self):
        return self._cards.keys()

    @property
    def _is_odd(self):
        return len(self._cards) % 2


class DeckPanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        super(DeckPanel, self).__init__(*args, **kwargs)
        self._create_widgets()

        self._trump_card = None

        self.SetSizeHints(200, 150)

    def _create_widgets(self):
        self._opened_trump = wx.StaticBitmap(parent=self, pos=(0, 12))
        self._deck_top = HiddenCard(parent=self, pos=(50, 0))
        self._card_count = wx.StaticText(parent=self, pos=(70, 100))

        self._opened_trump.Hide()
        self._deck_top.Hide()

    def set_opened_trump(self, card):
        img = card_image_manager.get_image(card).ConvertToImage()
        img = img.Rotate90(clockwise=False)
        self._opened_trump.SetBitmap(img.ConvertToBitmap())

        self._trump_card = card

    def set_card_count(self, count):
        assert count >= 0

        self._deck_top.Show(count > 1)
        self._opened_trump.Show(count > 0)

        if count == 0:
            self._card_count.SetLabel(u'Козырь - %s' % str(self._trump_card))
        else:
            self._card_count.SetLabel(str(count))


class ControlSizer(wx.BoxSizer):
    TAKE = 'take'
    DISCARD = 'discard'
    ENOUGH = 'enough'

    def __init__(self, *args, **kwargs):
        self.parent = kwargs.pop('parent')
        super(ControlSizer, self).__init__(*args, **kwargs)
        self._take_button = wx.Button(parent=self.parent, label=u'Беру')
        self._discard_button = wx.Button(parent=self.parent, label=u'Бито')
        self._enough_button = wx.Button(parent=self.parent, label=u'Хватит')
        self.AddMany(
            [self._take_button, self._discard_button, self._enough_button]
        )
        self.hide_all()

    def set_on_take_button_click(self, handler):
        self._take_button.Bind(wx.EVT_BUTTON, handler)

    def set_on_discard_button_click(self, handler):
        self._discard_button.Bind(wx.EVT_BUTTON, handler)

    def set_on_enough_button_click(self, handler):
        self._enough_button.Bind(wx.EVT_BUTTON, handler)

    def hide_all(self):
        self._take_button.Hide()
        self._discard_button.Hide()
        self._enough_button.Hide()

    def show_button(self, button_name):
        assert button_name in (self.TAKE, self.DISCARD, self.ENOUGH)

        self.hide_all()
        if button_name == self.DISCARD:
            self._discard_button.Show()
        elif button_name == self.ENOUGH:
            self._enough_button.Show()
        elif button_name == self.TAKE:
            self._take_button.Show()

        self.Layout()
        self.parent.Layout()  # TODO Сомнительное решение.
