#!/usr/bin/env python

import atools


@atools.CLI(__name__)
def entrypoint() -> dict[str, object]:
    return locals()


if __name__ == '__main__':
    atools.CLI(__name__).run()
