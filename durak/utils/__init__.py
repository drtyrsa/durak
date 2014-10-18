# -*- coding: utf-8 -*-
import os
from durak.consts import HOME_DIR


def get_filename(filename):
    dir_path = os.path.join(os.path.expanduser('~'), HOME_DIR)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    return os.path.join(dir_path, filename)