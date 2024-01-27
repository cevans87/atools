#!/usr/bin/env python

import atools


@atools.CLI(submodules=True)
def entrypoint() -> dict[str, object]:
    return locals()
