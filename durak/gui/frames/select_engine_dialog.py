# -*- coding: utf-8 -*-
import wx

from durak import consts
from durak.gui.frames.new_engine_dialog import NewEngineDialog
from durak.utils import get_setting, set_setting


class SelectEngineDialog(wx.Dialog):
    WIDTH = 400
    HEIGHT = 300

    def __init__(self):
        super(SelectEngineDialog, self).__init__(parent=None)
        self.SetSize((self.WIDTH, self.HEIGHT))
        self.SetTitle(u'Управление движками')

        self._selected_engine = None
        self.selected_engine = None

        self._create_layout()

    def _create_layout(self):
        self._panel = wx.Panel(parent=self)

        self._info_text = wx.StaticText(parent=self._panel)
        self._info_text.SetSizeHints(400, 50)
        self._list_box = wx.ListBox(
            self._panel,
            style=wx.LB_SINGLE
        )
        self._list_box.Bind(wx.EVT_LISTBOX, self._on_engine_select)

        self._add_button = wx.Button(
            parent=self._panel,
            label=u'Добавить движок'
        )
        self._add_button.Bind(wx.EVT_BUTTON, self._on_add_engine)

        self._remove_button = wx.Button(
            parent=self._panel,
            label=u'Удалить выбранный движок'
        )
        self._remove_button.Bind(wx.EVT_BUTTON, self._on_remove)
        self._ok_button = wx.Button(
            parent=self._panel,
            label=u'Готово'
        )
        self._ok_button.Bind(wx.EVT_BUTTON, self._on_ok)

        self._buttons_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._buttons_sizer.AddMany((self._remove_button, self._add_button))

        self._main_sizer = wx.FlexGridSizer(cols=1, rows=4)
        self._main_sizer.AddGrowableCol(0)
        self._main_sizer.AddGrowableRow(1)
        self._main_sizer.Add(self._info_text, flag=wx.ALIGN_LEFT)
        self._main_sizer.Add(self._list_box, flag=wx.EXPAND, proportion=1)
        self._main_sizer.Add(self._buttons_sizer, flag=wx.ALIGN_RIGHT)
        self._main_sizer.AddSpacer(15)
        self._main_sizer.Add(self._ok_button, flag=wx.ALIGN_RIGHT)

        self._panel.SetSizer(self._main_sizer)

        self._load_engine_list()

        self.Refresh()
        self.Layout()

    def _on_ok(self, event):
        selected_item = self._list_box.Selection

        engines = get_setting(consts.ENGINES_SETTING, consts.DEFAULT_ENGINES)
        for index, engine_data in enumerate(engines):
            if index == selected_item:
                engine_data['selected'] = True
            else:
                engine_data.pop('selected', None)
        set_setting(consts.ENGINES_SETTING, engines)

        self.selected_engine = self._selected_engine
        self.Close()

    def _load_engine_list(self):
        self._list_box.Clear()

        engines = get_setting(consts.ENGINES_SETTING, consts.DEFAULT_ENGINES)
        for i, engine_data in enumerate(engines):
            self._list_box.Append(engine_data['name'], engine_data)
            if engine_data.get('selected'):
                self._list_box.Select(i)

        self._on_engine_select()

    def _on_add_engine(self, event):
        dialog = NewEngineDialog()
        dialog.ShowModal()

        if dialog.engine_data:
            engine_list = get_setting(
                consts.ENGINES_SETTING, consts.DEFAULT_ENGINES
            )
            engine_list.append(dialog.engine_data)
            set_setting(consts.ENGINES_SETTING, engine_list)
            self._load_engine_list()

        dialog.Destroy()

    def _on_engine_select(self, event=None):
        if not self._info_text:
            return

        self._ok_button.Enable()

        selected_item = self._list_box.Selection

        # для движков по-умолчанию скрываем кнопку удаления
        self._remove_button.Enable(selected_item >= len(consts.DEFAULT_ENGINES))

        if selected_item == -1:
            self._selected_engine = None
            self._set_info_text(
                u'Выберите движок из списка или добавьте новый'
            )
            self._ok_button.Disable()
            self._remove_button.Disable()
            return

        engine_data = self._list_box.GetClientData(selected_item)
        new_selected_engine = engine_data['path']
        info_text = u'Выбран движок %s' % engine_data['name']
        if (self._selected_engine and
                self._selected_engine != new_selected_engine):
            info_text += u'\nЧтобы играть с ним, нужно начать новую игру.'

        self._set_info_text(info_text)
        self._selected_engine = new_selected_engine

    def _on_remove(self, event):
        selected_item = self._list_box.Selection
        if selected_item == -1:
            return

        engines = get_setting(consts.ENGINES_SETTING, consts.DEFAULT_ENGINES)
        del engines[selected_item]
        set_setting(consts.ENGINES_SETTING, engines)

        self._load_engine_list()

    def _set_info_text(self, text):
        self._info_text.SetLabel(text)
        self._info_text.Wrap(self.WIDTH)
