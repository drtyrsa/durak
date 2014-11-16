# -*- coding: utf-8 -*-
import os.path

current_dir = os.path.dirname(os.path.realpath(__file__))
ASSETS_PATH = os.path.join(current_dir, 'assets')

CARDS_IMAGE_PATH = os.path.join(ASSETS_PATH, 'cards.gif')
CARDS_HIDDEN_IMAGE_PATH = os.path.join(ASSETS_PATH, 'hidden.gif')

CARD_WIDTH = 71
CARD_HEIGHT = 96

HOME_DIR = '.durak'
SETTINGS_FILENAME = 'settings.json'