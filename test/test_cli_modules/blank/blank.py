#!/usr/bin/env python

from atools import cli


@cli
def main() -> dict[str, ...]:
    return locals()
