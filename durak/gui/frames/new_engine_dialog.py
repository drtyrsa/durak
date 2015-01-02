# -*- coding: utf-8 -*-
import wx


class NewEngineDialog(wx.Dialog):
    WIDTH = 300
    HEIGHT = 140

    def __init__(self):
        super(NewEngineDialog, self).__init__(parent=None)
        self.SetSize((self.WIDTH, self.HEIGHT))
        self.SetTitle(u'Добавить новый движок')

        self.engine_data = {}

        self._create_layout()

    def _create_layout(self):
        self._panel = wx.Panel(parent=self)

        self._name_label = wx.StaticText(self._panel, label=u'Имя движка')
        self._name_text_ctrl = wx.TextCtrl(self._panel, size=(250, 28))
        self._name_text_ctrl.Bind(wx.EVT_TEXT, self._validate)

        self._path_label = wx.StaticText(
            self._panel, label=u'Путь к исполняемому файлу движка'
        )
        self._path_text_ctrl = wx.TextCtrl(self._panel, size=(200, 28))
        self._path_text_ctrl.Bind(wx.EVT_TEXT, self._validate)

        self._open_button = wx.Button(
            parent=self._panel,
            label=u'Открыть...'
        )
        self._open_button.Bind(wx.EVT_BUTTON, self._on_open)
        self._ok_button = wx.Button(
            parent=self._panel,
            label=u'Готово'
        )
        self._ok_button.Bind(wx.EVT_BUTTON, self._on_ok)

        self._path_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._path_sizer.AddMany((self._path_text_ctrl, self._open_button))

        self._main_sizer = wx.BoxSizer(wx.VERTICAL)
        self._main_sizer.AddMany((
            self._name_label,
            self._name_text_ctrl,
        ))
        self._main_sizer.AddSpacer(5)
        self._main_sizer.AddMany((
            self._path_label,
            self._path_sizer,
        ))
        self._main_sizer.AddSpacer(15)
        self._main_sizer.Add(self._ok_button, flag=wx.ALIGN_RIGHT)

        self._panel.SetSizer(self._main_sizer)

        self.Refresh()
        self.Layout()

        self._validate()

    def _on_ok(self, event):
        self.engine_data = {
            'name': self._name_text_ctrl.GetValue(),
            'path': self._path_text_ctrl.GetValue()
        }
        self.Close()

    def _on_open(self, event):
        dialog = wx.FileDialog(
            self, u'Выберите файл движка', '', '', '*', wx.OPEN
        )
        if dialog.ShowModal() != wx.ID_OK:
            return

        filename = dialog.GetPath()
        dialog.Destroy()

        self._path_text_ctrl.SetValue(filename)

    def _validate(self, event=None):
        is_valid = bool(
            self._path_text_ctrl.GetValue() and
            self._name_text_ctrl.GetValue()
        )
        self._ok_button.Enable(is_valid)
