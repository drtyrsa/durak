# -*- coding: utf-8 -*-
import wx

from durak.controller import GameController
from durak.engine.wrapper import EngineWrapper
from durak.gui.widgets import (CardSizer, EnemyCardSizer, TablePanel,
                               DeckPanel, ControlSizer)
from durak.utils import get_filename


class PlayFrame(wx.Frame):
    WIDTH = 800
    HEIGHT = 450

    HUMAN = GameController.PLAYER1
    ENGINE = GameController.PLAYER2

    def __init__(self):
        super(PlayFrame, self).__init__(
            parent=None,
            title='Durak',
            size=(self.WIDTH, self.HEIGHT)
        )

        self._create_layout()

        self._controller = GameController(
            player1_name='HUMAN',
            player2_name='ENGINE',
            log_filename=get_filename('last_game'),
            overwrite_log=True
        )
        self._engine = None
        self._trump = None

        self._start_new_game()

    def _create_layout(self):
        self.Bind(wx.EVT_CLOSE, self._on_close)

        self._panel = wx.Panel(parent=self)

        self._top_player_sizer = EnemyCardSizer(
            wx.HORIZONTAL, parent=self._panel
        )
        self._bottom_player_sizer = CardSizer(
            wx.HORIZONTAL,
            parent=self._panel,
            on_click=self._on_bottom_player_card_click
        )

        self._table_sizer = wx.FlexGridSizer(cols=2, rows=1)
        self._table_sizer.AddGrowableCol(0)

        self._table = TablePanel(parent=self._panel)
        self._table_sizer.Add(self._table, proportion=1)

        self._deck = DeckPanel(self._panel, size=(100, 130))
        self._table_sizer.Add(self._deck)

        self._control_sizer = ControlSizer(wx.HORIZONTAL, parent=self._panel)
        self._control_sizer.set_on_discard_button_click(
            self._on_discard_button_click
        )
        self._control_sizer.set_on_enough_button_click(
            self._on_enough_button_click
        )
        self._control_sizer.set_on_take_button_click(
            self._on_take_button_click
        )

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
        self.Layout()
        self.Refresh()

    def _create_menu(self):
        self.menu = wx.MenuBar()
        menu = wx.Menu()  # Игра
        item = menu.Append(wx.ID_NEW, u'Новая игра', u'Начать новую игру')
        self.Bind(wx.EVT_MENU, self._start_new_game, item)
        item = menu.Append(wx.ID_EXIT, u'Выход', u'Выйти из игры')
        self.Bind(wx.EVT_MENU, self._on_close, item)
        self.menu.Append(menu, u'Игра')

        menu = wx.Menu()  # Настройки
        self._by_winner_menu_item = menu.AppendCheckItem(
            wx.ID_ANY,
            u'Ход под дурака',
            u'В новой игре ходит первым победитель в предыдущей'
        )
        self.Bind(wx.EVT_MENU, None, self._by_winner_menu_item)
        self.menu.Append(menu, u'Настройки')

        self.SetMenuBar(self.menu)

    def _on_close(self, event):
        self._stop_engine()
        if event.GetEventType() in wx.EVT_CLOSE.evtType:
            event.Skip()
        else:
            self.Close()

    def _start_new_game(self, event=None):
        self._stop_engine()
        self._engine = EngineWrapper('durak-dummy')

        new_game_data = self._controller.start_new_game(
            ignore_winner=not self._by_winner_menu_item.IsChecked()
        )
        self._trump = new_game_data['trump']

        self._deck.set_card_count(self._controller.deck_count)
        self._deck.set_opened_trump(self._trump)

        self._engine.init(self._trump)
        self._engine.deal(
            new_game_data['player2_cards'],
            self._controller.get_game_data_for(self.ENGINE)
        )
        self._top_player_sizer.set_count(len(new_game_data['player2_cards']))

        self._table.remove_all()

        self._bottom_player_sizer.remove_all()
        self._bottom_player_sizer.trump = self._trump
        for card in new_game_data['player1_cards']:
            self._bottom_player_sizer.add_card(card)
        self._bottom_player_sizer.Layout()

        self._set_enabled_cards_and_controls()

        self._panel.Layout()
        self.Layout()
        self.Refresh()

        if self._controller.to_move == self.ENGINE:
            self._engine_move()

    def _set_enabled_cards_and_controls(self):
        human_cards = self._bottom_player_sizer.cards
        on_table = self._table.cards
        self._control_sizer.hide_all()

        if (self._controller.to_move == self.HUMAN and
                self._controller.state == self._controller.States.MOVING):
            self._bottom_player_sizer.set_enabled_cards(
                human_cards.cards_that_can_be_added_to(on_table)
            )
            if on_table:
                self._control_sizer.show_button(self._control_sizer.DISCARD)
                self.SetStatusText(u'Подкидывайте еще, если есть')
            else:
                self.SetStatusText(u'Ходите')
        elif (self._controller.to_move == self.HUMAN and
                self._controller.state == self._controller.States.GIVING_MORE):
            self._bottom_player_sizer.set_enabled_cards(
                human_cards.cards_that_can_be_added_to(on_table)
            )
            self._control_sizer.show_button(self._control_sizer.ENOUGH)
            self.SetStatusText(u'Беру. Подкидывайте еще, если есть')
        elif (self._controller.to_move == self.ENGINE and
                self._controller.state == self._controller.States.RESPONDING):
            assert on_table

            self._bottom_player_sizer.set_enabled_cards(
                human_cards.cards_that_can_beat(on_table[-1])
            )
            self._control_sizer.show_button(self._control_sizer.TAKE)
            self.SetStatusText(u'Отбивайтесь')
        else:
            self._bottom_player_sizer.disable_all()
            self.SetStatusText(u'Думаю...')

    def _on_bottom_player_card_click(self, event):
        card = event.GetEventObject().card
        call_next = None

        if self._controller.state == self._controller.States.MOVING:
            self._controller.register_move(card)
            self._table.move(card)
            call_next = self._engine_respond
        elif self._controller.state == self._controller.States.RESPONDING:
            self._controller.register_response(card)
            self._table.respond(card)
            call_next = self._engine_move
        elif self._controller.state == self._controller.States.GIVING_MORE:
            self._table.give_more(card)

        self._bottom_player_sizer.remove_card(card, do_layout=True)
        self._set_enabled_cards_and_controls()

        self._check_for_game_over()

        if self._controller.state is not None and call_next is not None:
            call_next()

    def _on_discard_button_click(self, event):
        assert self._controller.to_move == self.HUMAN
        assert self._controller.state == self._controller.States.MOVING

        self._control_sizer.hide_all()
        self._controller.register_move(None)
        self._check_for_game_over()
        if self._controller.state == self._controller.States.DEALING:
            self._deal()
            self._engine_move()

    def _on_enough_button_click(self, event):
        assert self._controller.to_move == self.HUMAN
        assert self._controller.state == self._controller.States.GIVING_MORE

        self._control_sizer.hide_all()
        self._controller.register_give_more(self._table.given_more)
        self._check_for_game_over()
        if self._controller.state == self._controller.States.DEALING:
            self._deal()

    def _on_take_button_click(self, event):
        assert self._controller.to_move == self.ENGINE
        assert self._controller.state == self._controller.States.RESPONDING

        self._control_sizer.hide_all()
        self._controller.register_response(None)
        cards = self._engine.give_more(
            self._controller.on_table,
            self._controller.get_game_data_for(self.ENGINE)
        )

        # Здесь решается следующая задача: если движку есть, что подкинуть,
        # мы показываем карты на столе полсекунды, а только потом заканчиваем
        # ход. Использовать time.sleep здесь нельзя, т. к. он заблокирует
        # весь GUI. Поэтому используем колбек.
        if cards:
            for card in cards:
                self._table.give_more(card)

            delay = 500
        else:
            delay = 0

        def _rest_of_the_method():
            self._controller.register_give_more(self._table.given_more)
            self._check_for_game_over()
            if self._controller.state == self._controller.States.DEALING:
                self._deal()
                self._engine_move()

        wx.CallLater(delay, _rest_of_the_method)

    def _engine_respond(self):
        assert self._controller.state == self._controller.States.RESPONDING
        assert self._controller.to_move == self.HUMAN

        card = self._engine.respond(
            self._controller.on_table,
            self._controller.get_game_data_for(self.ENGINE)
        )
        self._controller.register_response(card)

        if card:
            self._table.respond(card)
            self._top_player_sizer.decrement()

        if self._controller.state == self._controller.States.DEALING:
            self._deal()
            self._engine_move()
        else:
            self._set_enabled_cards_and_controls()
            self._check_for_game_over()

    def _engine_move(self):
        assert self._controller.state == self._controller.States.MOVING
        assert self._controller.to_move == self.ENGINE

        card = self._engine.move(
            self._controller.on_table,
            self._controller.get_game_data_for(self.ENGINE)
        )
        self._controller.register_move(card)

        if card:
            self._table.move(card)
            self._top_player_sizer.decrement()

        if self._controller.state == self._controller.States.DEALING:
            self._deal()
        else:
            self._set_enabled_cards_and_controls()
            self._check_for_game_over()

    def _deal(self):
        deal_data = self._controller.deal()
        self._engine.deal(
            deal_data['player2_cards'],
            self._controller.get_game_data_for(self.ENGINE)
        )
        self._top_player_sizer.set_count(len(deal_data['player2_cards']))

        self._table.remove_all()

        self._deck.set_card_count(self._controller.deck_count)

        cards_added = (
            deal_data['player1_cards'] - self._bottom_player_sizer.cards
        )
        for card in cards_added:
            self._bottom_player_sizer.add_card(card)
        self._bottom_player_sizer.Layout()

        self._set_enabled_cards_and_controls()

    def _check_for_game_over(self):
        if not self._controller.is_game_over():
            return

        wx.CallLater(0, self._new_game_dialog)

    def _new_game_dialog(self):
        if self._controller.winner == self.HUMAN:
            text = u'Победа!'
        elif self._controller.winner == self.ENGINE:
            text = u'Вы проиграли.'
        else:
            text = u'Ничья.'

        dialog = wx.MessageDialog(
            None,
            u'%s Сыграем еще раз?' % text,
            u'Игра окончена',
            wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION
        )
        if (dialog.ShowModal() == wx.ID_YES):
            self._start_new_game()
        else:
            self.Close()

    def _stop_engine(self):
        if self._engine is not None:
            self._engine.game_end()
            self.engine = None
