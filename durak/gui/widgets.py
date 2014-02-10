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
