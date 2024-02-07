#!/usr/bin/env python3

import atools


@atools.CLI(__name__)
def entrypoint(
    positional_only: int,
    /,
    positional_or_keyword: int,
    *,
    keyword_only: int
) -> dict[str, int]:
    return locals()


if __name__ == '__main__':
    atools.CLI(__name__).run()
