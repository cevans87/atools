#!/usr/bin/env python

from atools import cli


@cli
async def entrypoint(answer: int) -> dict[str, int]:
    return locals()
