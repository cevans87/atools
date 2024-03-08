import concurrent.futures
import datetime
import time

import atools


@atools.Throttle(keygen=lambda arg: arg)
def foo(arg) -> None:
    print(f'{datetime.datetime.now()}')
    time.sleep(1)


with concurrent.futures.ThreadPoolExecutor(max_workers=1024) as executor:
    for _ in range(1024):
        executor.submit(foo)


time.sleep(600)
