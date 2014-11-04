#!/usr/bin/env python
# -*- coding: utf-8 -*-
import wx

from durak.gui.frames import ViewLogFrame


def main():
    app = wx.PySimpleApp()
    frame = ViewLogFrame()
    frame.Show()
    app.MainLoop()

if __name__ == '__main__':
    main()