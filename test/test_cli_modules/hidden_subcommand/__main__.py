#!/usr/bin/env python

import importlib

import atools


if __name__ == '__main__':
    importlib.import_module('hidden_subcommand')
    atools.CLI(name=__package__).run()
