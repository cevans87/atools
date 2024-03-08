import datetime

import atools


@atools.Throttle(max_window=1, window=1.0)
def foo() -> None:
    print(f'{datetime.datetime.now()}')


while True:
    foo()
