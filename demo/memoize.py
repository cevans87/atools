#!/usr/bin/env python3

import os
import pathlib
import pprint

import atools


@atools.CLI(__name__)
def entrypoint() -> None:
    pprint.pprint(f'{os.environ.__dict__=}')


if __name__ == '__main__':
    import sys
    atools.CLI(__name__).run()
