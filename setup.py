# -*- coding: utf-8 -*-
import multiprocessing  # http://bugs.python.org/issue15881#msg170215
from setuptools import setup


def show_readme():
    with open('README.rst') as f:
        return f.read()


setup(
    name='durak',
    version='0.1',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2.7',
        'Topic :: Games/Entertainment :: Board Games',
    ],
    description='Durak card game',
    long_description=show_readme(),
    url='http://github.com/drtyrsa/',
    author='Vlad Starostin',
    author_email='drtyrsa@yandex.ru',
    license='MIT',
    packages=['durak'],
    entry_points={
        'console_scripts': [
            'durak-autoplay=durak.autoplay:main',
            'durak-dummy=durak.engine.dummy:main',
            'durak-gui=durak.gui.play_app:main',
            'durak-logviewer=durak.gui.view_log_app:main',
        ],
    },
    install_requires=[
        'docopt',
    ],
    test_suite='nose.collector',
    tests_require=['nose', 'mock'],
    zip_safe=False
)
