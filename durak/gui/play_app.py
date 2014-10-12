#!/usr/bin/env python
# -*- coding: utf-8 -*-
import wx

from durak.gui.frames import PlayFrame


def main():
    app = wx.PySimpleApp()
    frame = PlayFrame()
    frame.Show()
    app.MainLoop()

if __name__ == '__main__':
    main()