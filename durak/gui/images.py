# -*- coding: utf-8 -*-
import wx

from durak.utils.cards import DurakCard
from durak.consts import CARDS_IMAGE_PATH, CARD_WIDTH, CARD_HEIGHT


class CardImageManager(object):
    def __init__(self, image_path, card_width, card_height):
        self._image_path = image_path
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

        wx_bitmap.Destroy()

    def get_image(self, card):
        if not self._data:
            self._prepare_data()

        return self._data[card]


card_image_manager = CardImageManager(
    CARDS_IMAGE_PATH, CARD_WIDTH, CARD_HEIGHT
)