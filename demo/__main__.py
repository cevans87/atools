#!/usr/bin/env python3
"""Demo for package-level main.

Ex.

```bash
python3 -m demo -h
```

"""

import atools

from . import advanced, cli, first_example, memoize, rate

atools.CLI(__package__).run()
