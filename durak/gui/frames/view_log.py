# -*- coding: utf-8 -*-
import os.path

import wx

from durak.gamelogger import LogViewer
from durak.gui.widgets import LabeledCardSizer, TablePanel, DeckPanel
from durak.utils import get_setting, set_setting


class ViewLogFrame(wx.Frame):
    WIDTH = 800
    HEIGHT = 500

    LAST_DIR_SETTING = 'last_log_dir'

    def __init__(self):
        super(ViewLogFrame, self).__init__(
            parent=None,
            title='Durak log viewer',
            size=(self.WIDTH, self.HEIGHT)
        )

        self._log_viever = None

        self._create_layout()

    def _create_layout(self):
        self.Bind(wx.EVT_CLOSE, self._on_close)

        self._panel = wx.Panel(parent=self)

        self._top_player_sizer = LabeledCardSizer(
            wx.HORIZONTAL,
            parent=self._panel,
        )
        self._bottom_player_sizer = LabeledCardSizer(
            wx.HORIZONTAL,
            parent=self._panel,
        )

        self._table_sizer = wx.FlexGridSizer(cols=2, rows=1)
        self._table_sizer.AddGrowableCol(0)

        self._table = TablePanel(parent=self._panel)
        self._table_sizer.Add(self._table, proportion=1)

        self._deck = DeckPanel(self._panel, size=(100, 130))
        self._table_sizer.Add(self._deck)

        self._control_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._to_game_start_button = wx.Button(parent=self._panel, label=u'<<')
        self._to_game_start_button.Bind(
            wx.EVT_BUTTON, self._menu_on_to_game_start
        )
        self._prev_button = wx.Button(parent=self._panel, label=u'<')
        self._prev_button.Bind(wx.EVT_BUTTON, self._menu_on_prev)
        self._next_button = wx.Button(parent=self._panel, label=u'>')
        self._next_button.Bind(wx.EVT_BUTTON, self._menu_on_next)
        self._to_game_end_button = wx.Button(parent=self._panel, label=u'>>')
        self._to_game_end_button.Bind(wx.EVT_BUTTON, self._menu_on_to_game_end)
        self._control_sizer.AddMany([
            self._to_game_start_button,
            self._prev_button,
            self._next_button,
            self._to_game_end_button
        ])

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

        self._create_menu()

        self._panel.Layout()
        self.Refresh()
        self.Layout()

        self.PLAYER_SIZER_MAP = {
            LogViewer.PLAYER1: self._bottom_player_sizer,
            LogViewer.PLAYER2: self._top_player_sizer,
        }

        self._menu_on_open()

    def _create_menu(self):
        self.menu = wx.MenuBar()
        menu = wx.Menu()  # Файл
        item = menu.Append(
            wx.ID_OPEN, u'Открыть файл лога...', u'Открыть файл лога'
        )
        self.Bind(wx.EVT_MENU, self._menu_on_open, item)
        item = menu.Append(
            wx.ID_ANY,
            u'Список игр...\tCTRL+L',
            u'Просмотреть список игр в открытом файле'
        )
        self.Bind(wx.EVT_MENU, self._menu_on_select_game, item)
        item = menu.Append(wx.ID_EXIT, u'Выход', u'Закрыть программу')
        self.Bind(wx.EVT_MENU, self._on_close, item)
        self.menu.Append(menu, u'Файл')

        menu = wx.Menu()  # Текущая игра
        self._to_game_start_menu_item = menu.Append(
            wx.ID_ANY, u'В начало <<\tHOME', u'Перейти в начало игры'
        )
        self.Bind(
            wx.EVT_MENU,
            self._menu_on_to_game_start,
            self._to_game_start_menu_item
        )
        self._prev_menu_item = menu.Append(
            wx.ID_ANY, u'Назад <\tCTRL+LEFT', u'Вернуться на ход назад'
        )
        self.Bind(wx.EVT_MENU, self._menu_on_prev, self._prev_menu_item)
        self._next_menu_item = menu.Append(
            wx.ID_ANY, u'Вперед >\tCTRL+RIGHT', u'Перейти на ход вперед'
        )
        self.Bind(wx.EVT_MENU, self._menu_on_next, self._next_menu_item)
        self._to_game_end_menu_item = menu.Append(
            wx.ID_ANY, u'В конец >>\tEND', u'Перейти в конец игры'
        )
        self.Bind(
            wx.EVT_MENU,
            self._menu_on_to_game_end,
            self._to_game_end_menu_item
        )
        self.menu.Append(menu, u'Текущая игра')

        self.SetMenuBar(self.menu)

    def _on_close(self, event):
        if event.GetEventType() in wx.EVT_CLOSE.evtType:
            event.Skip()
        else:
            self.Close()

    def _menu_on_open(self, event=None):
        last_directory = get_setting(
            self.LAST_DIR_SETTING, os.path.expanduser('~')
        )
        dialog = wx.FileDialog(
            self, u'Выберите файл лога', last_directory, '', '*', wx.OPEN
        )
        if dialog.ShowModal() != wx.ID_OK:
            self.Close()

        filename = dialog.GetPath()
        dialog.Destroy()

        self._log_viever = LogViewer(filename)
        set_setting(self.LAST_DIR_SETTING, os.path.dirname(filename))

        self._menu_on_select_game()

    def _menu_on_select_game(self, event=None):
        choices = [
            '%d. %s' % (i, game['title']) for i, game
            in enumerate(self._log_viever.iterindex(), start=1)
        ]
        dialog = wx.SingleChoiceDialog(
            self,
            u'Выберите игру',
            u'Список игр',
            choices,
            wx.CHOICEDLG_STYLE,
        )
        dialog.SetSize((500, 400))
        dialog.Refresh()
        if dialog.ShowModal() == wx.ID_OK:
            self._log_viever.load_game(dialog.GetSelection())
            self._bottom_player_sizer.set_label(self._log_viever.player1_name)
            self._top_player_sizer.set_label(self._log_viever.player2_name)
            self._menu_on_to_game_start()

        dialog.Destroy()

    def _menu_on_to_game_start(self, event=None):
        self._log_viever.to_game_start()

        if not self._log_viever.has_next:
            return

        self._deck.set_opened_trump(self._log_viever.opened_trump)

        for card_sizer in (self._bottom_player_sizer, self._top_player_sizer):
            card_sizer.trump = self._log_viever.opened_trump
            card_sizer.remove_all()

        log_event = self._log_viever.get_next()
        self._new_move(log_event)

        self._panel.Layout()
        self.Layout()
        self.Refresh()

        self._set_enabled_controls()

    def _menu_on_to_game_end(self, event=None):
        self._log_viever.to_game_end()

        if not self._log_viever.has_prev:
            return

        log_event = self._log_viever.get_prev()
        self._new_move(log_event, with_table=True)

        self._set_enabled_controls()

    def _menu_on_next(self, event):
        if not self._log_viever.has_next:
            return

        log_event = self._log_viever.get_next()
        if log_event['event_type'] == self._log_viever.NEW_MOVE:
            self._new_move(log_event)
            return

        card_sizer = self.PLAYER_SIZER_MAP[log_event['to_move']]
        table_method = getattr(self._table, log_event['event_type'])

        card = log_event['card']
        table_method(card)
        card_sizer.remove_card(card, do_layout=True)

        self._set_enabled_controls()

    def _menu_on_prev(self, event):
        if not self._log_viever.has_prev:
            return

        log_event = self._log_viever.get_prev()
        if log_event['event_type'] == self._log_viever.NEW_MOVE:
            self._new_move(log_event, with_table=True)
            return

        card_sizer = self.PLAYER_SIZER_MAP[log_event['to_move']]

        card = log_event['card']
        self._table.pop()
        card_sizer.add_card(card, do_layout=True)

        self._set_enabled_controls()

    def _new_move(self, log_event, with_table=False):
        assert log_event['event_type'] == self._log_viever.NEW_MOVE

        self._table.remove_all()
        self._deck.set_card_count(log_event['deck_count'])

        if with_table:
            for index, card in enumerate(log_event['moves_and_responds']):
                if index % 2:
                    self._table.respond(card)
                else:
                    self._table.move(card)


            for card in log_event['given_more']:
                self._table.give_more(card)


        card_sizers = (self._bottom_player_sizer, self._top_player_sizer)
        card_sets = (log_event['player1_cards'], log_event['player2_cards'])

        for card_sizer, card_set in zip(card_sizers, card_sets):
            if with_table:
                card_sizer.remove_all()
                cards_to_add = card_set - set(
                    log_event['moves_and_responds'] + log_event['given_more']
                )
            else:
                cards_to_add = card_set - card_sizer.cards

            for card in cards_to_add:
                card_sizer.add_card(card)
            card_sizer.Layout()

        if log_event['to_move'] == self._log_viever.PLAYER1:
            self.SetStatusText(u'Атакует игрок снизу')
        else:
            self.SetStatusText(u'Атакует игрок сверху')

        self._set_enabled_controls()

    def _set_enabled_controls(self):
        all_controls = {
            self._to_game_start_button,
            self._to_game_end_button,
            self._next_button,
            self._prev_button,
            self._to_game_end_menu_item,
            self._to_game_start_menu_item,
            self._prev_menu_item,
            self._next_menu_item,
        }
        [control.Enable(False) for control in all_controls]

        if not self._log_viever or not self._log_viever.has_game_loaded:
            return

        if self._log_viever.has_prev:
            self._to_game_start_button.Enable()
            self._prev_button.Enable()
            self._to_game_start_menu_item.Enable()
            self._prev_menu_item.Enable()

        if self._log_viever.has_next:
            self._to_game_end_button.Enable()
            self._next_button.Enable()
            self._to_game_end_menu_item.Enable()
            self._next_menu_item.Enable()
