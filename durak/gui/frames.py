# -*- coding: utf-8 -*-
import wx

from durak.gui.widgets import (CardSizer, EnemyCardSizer, TablePanel,
                               DeckPanel, ControlSizer)


class PlayFrame(wx.Frame):
    WIDTH = 800
    HEIGHT = 450

    def __init__(self):
        super(PlayFrame, self).__init__(
            parent=None,
            title='Durak',
            size=(self.WIDTH, self.HEIGHT)
        )

        self._create_layout()

    def _create_layout(self):
        self._panel = wx.Panel(parent=self)

        self._top_player_sizer = EnemyCardSizer(
            wx.HORIZONTAL, parent=self._panel
        )
        self._bottom_player_sizer = CardSizer(
            wx.HORIZONTAL, parent=self._panel, on_click=lambda e: e
        )

        self._table_sizer = wx.FlexGridSizer(cols=2, rows=1)
        self._table_sizer.AddGrowableCol(0)

        self._table = TablePanel(parent=self._panel)
        self._table_sizer.Add(self._table, proportion=1)

        self._deck = DeckPanel(self._panel, size=(100, 130))
        self._table_sizer.Add(self._deck)

        self._control_sizer = ControlSizer(wx.HORIZONTAL, parent=self._panel)

        self._main_sizer = wx.FlexGridSizer(cols=1, rows=4)
        self._main_sizer.AddGrowableCol(0)
        self._main_sizer.AddGrowableRow(1)
        self._main_sizer.Add(
            self._top_player_sizer, flag=wx.EXPAND, proportion=1
        )
        self._main_sizer.Add(
            self._table_sizer, flag=wx.ALIGN_CENTER_VERTICAL, proportion=1
        )
        self._main_sizer.Add(self._control_sizer, flag=wx.EXPAND, proportion=1)
        self._main_sizer.Add(
            self._bottom_player_sizer, flag=wx.EXPAND, proportion=1
        )

        self._panel.SetSizer(self._main_sizer)

        self.CreateStatusBar()

        self._panel.Layout()
        self.Layout()
        self.Refresh()
