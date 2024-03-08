import concurrent.futures
import datetime
import time

import atools


@atools.Throttle(value=1, max_=2, window=1.0)
def foo(arg) -> None:
    print(f'{datetime.datetime.now()}')
    time.sleep(1)


with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
    for _ in executor.map(foo, range(1024)):
        pass


time.sleep(600)
