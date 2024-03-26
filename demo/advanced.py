#!/usr/bin/env python3
"""Demos for advanced composition of atools decorators.
"""

import atools


# Run with any of the following:
# - python3 -m demo.advanced entrypoint
# - python3 -m demo advanced entrypoint
@atools.CLI()
def entrypoint() -> None:
    print('haha')


# Run with any of the following:
# - python3 -m demo advanced burst [arg]...
# - python3 -m demo.advanced burst [arg]...
#
# A few cool things to try:
# - python3 -m demo advanced burst
@atools.CLI()
def burst(foo: int) -> None:
    ...


# Enables this CLI to be run with `python3 -m demo.advanced`.
if __name__ == '__main__':
    atools.CLI().run(__name__)
