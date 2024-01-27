#!/usr/bin/env python3

import atools


@atools.CLI(submodules=True)
def entrypoint() -> dict[str, bool]:
    return locals()
