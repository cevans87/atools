#!/usr/bin/env python

import importlib

import atools


if __name__ == '__main__':
    importlib.import_module('flag_types.with_default')
    importlib.import_module('flag_types.without_default')
    atools.CLI('flag_types').run()
