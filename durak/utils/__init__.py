# -*- coding: utf-8 -*-
import json
import os

from durak.consts import HOME_DIR, SETTINGS_FILENAME


def get_filename(filename):
    dir_path = os.path.join(os.path.expanduser('~'), HOME_DIR)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    return os.path.join(dir_path, filename)


def get_setting(setting_name, default=None):
    settings_filename = get_filename(SETTINGS_FILENAME)

    if not os.path.exists(settings_filename):
        return default

    with open(settings_filename, 'r') as f:
        json_data = json.load(f)

    return json_data.get(setting_name, default)


def set_setting(setting_name, value):
    settings_filename = get_filename(SETTINGS_FILENAME)

    if os.path.exists(settings_filename):
        with open(settings_filename, 'r+') as f:
            json_data = json.load(f)
            json_data[setting_name] = value

            f.seek(0)
            json.dump(json_data, f)
            f.truncate()
    else:
        with open(settings_filename, 'w') as f:
            json_data = {}
            json_data[setting_name] = value
            json.dump(json_data, f)
