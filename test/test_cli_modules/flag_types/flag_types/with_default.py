#!/usr/bin/env python3

import atools


@atools.CLI(__name__)
def entrypoint(
    positional_only_with_default: int = 0,
    /,
    positional_or_keyword_with_default: int = 1,
    *,
    keyword_only_with_default: int = 2
) -> dict[str, int]:
    return locals()


if __name__ == '__main__':
    atools.CLI(__name__).run()
