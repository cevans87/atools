#!/usr/bin/env python3
"""Demo for package-level main.

Ex.

```bash
python3 -m demo -h
```

"""

import logging

import atools

from . import advanced, cli, first_example, memoize, rate

logging.basicConfig(level=logging.CRITICAL, format='%(levelname)s: %(message)s')

atools.CLI(__package__).run()
