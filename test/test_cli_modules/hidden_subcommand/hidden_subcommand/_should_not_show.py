#!/usr/bin/env python

import atools


@atools.CLI()
def entrypoint(foo: str, /) -> dict[str, str]:
    return locals()
