#!/usr/bin/env python

from atools import cli
from logging import getLogger

logger = getLogger(__package__)


@cli
def main(foo: int = 0) -> dict[str, int]:
    return locals()
