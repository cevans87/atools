from asyncio import Semaphore as AsyncSemaphore, sleep as async_sleep
from collections import deque
from dataclasses import dataclass, field
from datetime import timedelta
from functools import partial, wraps
import inspect
from sys import maxsize
from threading import Lock as SyncLock, Semaphore as SyncSemaphore
from time import sleep as sync_sleep, time
from typing import Any, Callable, Optional, Union


@dataclass(frozen=True)
class _RateBase:
    fn: Callable
    size: int
    duration: Optional[timedelta]

    time_in: deque = field(init=False, default_factory=deque)
    
    def __post_init__(self) -> None:
        if self.duration is not None:
            for _ in range(self.size):
                self.time_in.append(-maxsize)

    def get_wait_time(self) -> int:
        if self.duration is None:
            wait_time = 0
        else:
            time_in = self.time_in.popleft()
            wait_time = max(self.duration.total_seconds() - (time() - time_in), 0)
            self.time_in.append(time() + wait_time)
        
        return wait_time


@dataclass(frozen=True)
class _AsyncRate(_RateBase):
    async_semaphore: AsyncSemaphore = field(init=False, default_factory=lambda: AsyncSemaphore())
    
    def __post_init__(self) -> None:
        super().__post_init__()
        self.async_semaphore._value = self.size

    @property
    def running(self) -> int:
        # noinspection PyProtectedMember,PyUnresolvedReferences
        return self.size - self.async_semaphore._value

    def get_decorator(self) -> Callable:
        async def decorator(*args, **kwargs) -> Any:
            async with self.async_semaphore:
                wait_time = self.get_wait_time()
                if wait_time > 0:
                    await async_sleep(wait_time)

                return await self.fn(*args, **kwargs)

        decorator.rate = self

        return decorator


@dataclass(frozen=True)
class _SyncRate(_RateBase):
    sync_lock: SyncLock = field(init=False, default_factory=lambda: SyncLock())
    sync_semaphore: SyncSemaphore = field(init=False, default_factory=lambda: SyncSemaphore())

    def __post_init__(self) -> None:
        super().__post_init__()
        self.sync_semaphore._value = self.size

    @property
    def running(self) -> int:
        with self.sync_lock:
            # noinspection PyProtectedMember,PyUnresolvedReferences
            return self.size - self.sync_semaphore._value

    def get_decorator(self) -> Callable:
        def decorator(*args, **kwargs):
            with self.sync_semaphore:
                wait_time = self.get_wait_time()
                if wait_time > 0:
                    sync_sleep(wait_time)

                return self.fn(*args, **kwargs)

        decorator.rate = self

        return decorator
    
    def get_wait_time(self) -> int:
        with self.sync_lock:
            return super().get_wait_time()


def rate(
        _fn: Optional[Callable] = None,
        *,
        size: int,
        duration: Optional[Union[int, float, timedelta]] = None
):
    """Function decorator that rate limits the number of calls to function.

    'size' must be provided. It specifies the maximum number of calls that may be made concurrently
      and optionally within a given 'duration' time window.

    If 'duration' is provided, the maximum number of calls is limited to 'size' calls in any given
      'duration' time window.

    Examples:
        - Only 2 concurrent calls allowed.
            @rate(size=2)
            def foo(): ...

        - Only 2 calls allowed per minute.
            @rate(size=2, duration=60)
            def foo(): ...

        - Same as above, but duration specified with a timedelta.
            @rate_window(size=2, duration=datetime.timedelta(minutes=1))
            def foo(): ...

        - Same as above, but async.
            @rate_window(size=2, duration=datetime.timedelta(minutes=1))
            async def foo(): ...
    """
    if _fn is None:
        return partial(rate, size=size, duration=duration)

    assert size > 0, 'Concurrency must be greater than 0'
    duration = timedelta(seconds=duration) if isinstance(duration, (int, float)) else duration

    if inspect.iscoroutinefunction(_fn):
        decorator = _AsyncRate(fn=_fn, size=size, duration=duration).get_decorator()
    else:
        decorator = _SyncRate(fn=_fn, size=size, duration=duration).get_decorator()
        
    return wraps(_fn)(decorator)
