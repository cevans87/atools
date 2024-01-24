#!/usr/bin/env python

def entrypoint(foo: str, /) -> dict[str, str]:
    return locals()
