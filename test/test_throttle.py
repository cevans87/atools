import datetime

import atools


def test_register() -> None:
    @atools.Throttle(window=datetime.timedelta(seconds=1))
    def foo():
        print('haha')
        ...

    while True:
        foo()
