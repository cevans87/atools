import asyncio
from asyncio import sleep as async_sleep
from atools.decorator_mixin import DecoratorMixin, Fn
from collections import deque
from datetime import timedelta
import inspect
import threading
from time import sleep as sync_sleep, time
from typing import Any, Optional, Union


class _Rate:
    """Function decorator that rate limits the number of calls to function.

    'size' must be provided. It specifies the maximum number of calls that may be made concurrently
      and optionally within a given 'duration' time window.

    If 'duration' is provided, the maximum number of calls is limited to 'size' calls in any given
      'duration' time window.

    if 'thread_safe' is True, the decorator is guaranteed to be thread safe.

    Examples:
        - Only 2 concurrent calls allowed.
            @rate(size=2)
            async def foo(): ...

        - Only 2 calls allowed per minute.
            @rate(size=2, duration=60)
            async def foo(): ...

        - Same as above, but duration specified with a timedelta.
            @rate_window(size=2, duration=datetime.timedelta(minutes=1))
            async def foo(): ...

        - Same as above, but thread safe.
            @rate_window(size=2, duration=datetime.timedelta(minutes=1), thread_safe=True)
            def foo(): ...
    """

    # These are only created if decorator is 'thread_safe'
    _sync_lock: Optional[threading.Lock] = None
    _sync_semaphore: Optional[threading.Semaphore] = None
    _sync_window_time_in: Optional[deque] = None

    def __init__(
            self,
            fn: Fn,
            *,
            size: int,
            duration: Optional[Union[int, timedelta]] = None,
            thread_safe: bool = False,
    ) -> None:
        assert size > 0, 'Concurrency must be greater than 0'

        self._fn = fn
        self._size = size
        self._duration = duration.total_seconds() if isinstance(duration, timedelta) else duration
        self._thread_safe = thread_safe

        self._async_waiters = 0
        self._async_semaphore_: Optional[asyncio.Semaphore] = None

        self._sync_waiters = 0
        if self._thread_safe:
            self._sync_lock = threading.Lock()
            self._sync_semaphore = threading.Semaphore(self._size)

        if self._duration is not None:
            self._async_window_time_in = deque()
            for _ in range(self._size):
                self._async_window_time_in.append(-self._duration)

            if self._thread_safe:
                self._sync_window_time_in = deque()
                for _ in range(self._size):
                    self._sync_window_time_in.append(-self._duration)

    async def __aenter__(self) -> None:
        self._async_waiters += 1
        try:
            await self._async_semaphore.acquire()
            if self._duration is not None:
                async_window_time_in = self._async_window_time_in.popleft()
                remaining = self._duration - (time() - async_window_time_in)
                if remaining > 0:
                    await async_sleep(remaining)

                self._async_window_time_in.append(time())
        finally:
            self._async_waiters -= 1

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._async_semaphore.release()

    def __enter__(self) -> None:
        if self._thread_safe:
            with self._sync_lock:
                self._sync_waiters += 1
            try:
                self._sync_semaphore.acquire()
                if self._duration is not None:
                    sync_window_time_in = self._sync_window_time_in.popleft()
                    remaining = self._duration - (time() - sync_window_time_in)
                    if remaining > 0:
                        sync_sleep(remaining)
                    self._sync_window_time_in.append(time())
            finally:
                with self._sync_lock:
                    self._sync_waiters -= 1

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._thread_safe:
            self._sync_semaphore.release()

    def __call__(self, *args, **kwargs) -> Any:
        with self:
            sync_return = self._fn(*args, **kwargs)

        if not inspect.iscoroutine(sync_return):
            return sync_return
        else:
            async def _call():
                async with self:
                    return await sync_return

            return _call()

    @property
    def _async_semaphore(self) -> asyncio.Semaphore:
        if self._async_semaphore_ is None:
            self._async_semaphore_ = asyncio.Semaphore(self._size)
        return self._async_semaphore_

    @property
    def async_waiters(self) -> int:
        return self._async_waiters

    @property
    def sync_waiters(self) -> int:
        with self._sync_lock:
            return self._sync_waiters


rate = type('rate', (DecoratorMixin, _Rate), {})
