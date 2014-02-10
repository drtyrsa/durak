# -*- coding: utf-8 -*-
import wx

from durak.gui.widgets import CardButton
from durak.utils.cards import DurakCard


class PlayFrame(wx.Frame):
    def __init__(self):
        super(PlayFrame, self).__init__(
            parent=None,
            title='Durak',
            size=(800, 450)
        )

        self._create_layout()

    def _create_layout(self):
        self._panel = wx.Panel(parent=self)
        self.test = CardButton(parent=self._panel, card=DurakCard('6D'))
