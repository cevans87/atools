#!/usr/bin/env python3

from atools import cli


@cli
def entrypoint() -> dict[str, bool]:
    return locals()
