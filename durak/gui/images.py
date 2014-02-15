# -*- coding: utf-8 -*-
import wx

from durak.utils.cards import DurakCard
from durak.consts import (CARDS_IMAGE_PATH, CARDS_HIDDEN_IMAGE_PATH,
                          CARD_WIDTH, CARD_HEIGHT)


class CardImageManager(object):
    HIDDEN = 'hidden'

    def __init__(self, image_path, hidden_image_path, card_width, card_height):
        self._image_path = image_path
        self._hidden_image_path = hidden_image_path
        self._card_width = card_width
        self._card_height = card_height
        self._data = {}

    def _prepare_data(self):
        wx_bitmap = (
            wx.Image(self._image_path, wx.BITMAP_TYPE_GIF).ConvertToBitmap()
        )

        for card in DurakCard.all():
            left_top_x = card.numeric_value * self._card_width
            left_top_y = card.numeric_suit * self._card_height
            self._data[card] = wx_bitmap.GetSubBitmap(
                (left_top_x, left_top_y, self._card_width, self._card_height)
            )

        hidden_bitmap = (
            wx.Image(self._hidden_image_path, wx.BITMAP_TYPE_GIF)
              .ConvertToBitmap()
        )
        self._data[self.HIDDEN] = hidden_bitmap

        wx_bitmap.Destroy()

    def _get_item(self, key):
        if not self._data:
            self._prepare_data()

        return self._data[key]

    def get_image(self, card):
        return self._get_item(card)

    def get_hidden_card_image(self):
        return self._get_item(self.HIDDEN)


card_image_manager = CardImageManager(
    CARDS_IMAGE_PATH, CARDS_HIDDEN_IMAGE_PATH, CARD_WIDTH, CARD_HEIGHT
)
