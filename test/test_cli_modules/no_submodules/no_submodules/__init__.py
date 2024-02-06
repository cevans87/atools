#!/usr/bin/env python

import atools


@atools.CLI()
def entrypoint(foo: int, /) -> dict[str, int]:
    return locals()
