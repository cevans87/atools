#!/usr/bin/env python3

def entrypoint(
    positional_only: int,
    /,
    positional_or_keyword: int,
    *,
    keyword_only: int
) -> dict[str, int]:
    return locals()
