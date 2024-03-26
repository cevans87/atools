#!/usr/bin/env python3
"""Demo for package-level main.

Ex.

```bash
python3 -m demo -h
```

"""

import logging

import atools

from . import advanced, cli

logging.basicConfig(level=logging.CRITICAL, format='%(levelname)s: %(message)s')

atools.CLI().run(__package__)
