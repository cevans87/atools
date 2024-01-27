#!/usr/bin/env python

import atools


@atools.CLI(submodules=False)
def entrypoint(foo: int, /) -> dict[str, int]:
    return locals()
