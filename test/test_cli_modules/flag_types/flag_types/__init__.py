#!/usr/bin/env python

from atools import cli
from logging import getLogger

logger = getLogger(__package__)


@cli
def main(foo: int, /) -> dict[str, int]:
    print(foo)
    return locals()
