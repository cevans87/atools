#!/usr/bin/env python

import atools


@atools.CLI(submodules=True)
def entrypoint(foo: int, /) -> dict[str, int]:
    return locals()
