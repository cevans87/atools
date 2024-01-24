#!/usr/bin/env python3

from atools import cli


@cli
def main(
    *var_positional: list[str],
    **var_keyword: dict[str, str],
) -> dict[str, list[str] | dict[str, str]]:
    return locals()
