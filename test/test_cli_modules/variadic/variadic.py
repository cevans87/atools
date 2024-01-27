#!/usr/bin/env python3

import atools


@atools.CLI()
def main(
    *var_positional: int,
    **var_keyword: int,
) -> dict[str, list[str] | dict[str, int]]:
    return locals()
