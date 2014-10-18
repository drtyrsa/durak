#!/bin/sh
nosetests --with-coverage --cover-erase --cover-inclusive --cover-package=durak && coverage html --include=durak* && google-chrome htmlcov/index.html
