#!/usr/bin/env python

from atools import cli


@cli
def entrypoint() -> dict[str, object]:
    return locals()
