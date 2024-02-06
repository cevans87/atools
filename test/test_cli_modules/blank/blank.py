#!/usr/bin/env python

import atools


@atools.CLI()
def entrypoint() -> dict[str, object]:
    return locals()
