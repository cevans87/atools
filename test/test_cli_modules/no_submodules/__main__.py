#!/usr/bin/env python

import importlib

import atools


if __name__ == '__main__':
    importlib.import_module('no_submodules')
    atools.CLI(__name__).run()