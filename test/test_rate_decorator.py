import asyncio
from asyncio import gather
from atools import async_test_case, rate
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import threading
from typing import Awaitable, Callable, Optional
import unittest
from unittest.mock import call, MagicMock, patch


@async_test_case
class TestRate(unittest.TestCase):

    def test_size_le_0_fails_assert(self) -> None:
        for size in [-1, 0]:
            with self.assertRaises(AssertionError):
                @rate(size=size)
                def foo() -> None:
                    ...

    def test_concurrent_size_limits_sync_concurrency_to_size(self) -> None:
        depth = 5
        body = MagicMock()

        def make_foo(foo_size: int, foo_next_foo: Optional[Callable]) -> Callable[..., Awaitable]:
            event = threading.Event()

            @rate(size=foo_size, thread_safe=True)
            def foo():
                while (not event.is_set()) and (foo.rate.sync_waiters != 1):
                    pass

                body(foo_size)
                event.set()

                if foo_next_foo is not None:
                    foo_next_foo()

            return foo

        next_foo: Optional[Callable] = None
        for size in range(1, depth):
            next_foo = make_foo(size, next_foo)

        futures = []
        with ThreadPoolExecutor(max_workers=depth) as executor:
            for _ in range(depth):
                futures.append(executor.submit(next_foo))

        body.assert_has_calls([
            call(repeat)
            for repeat in range(1, depth)
            for _ in range(repeat)
        ], any_order=True)

    async def test_concurrent_size_limits_async_concurrency_to_size(self) -> None:
        depth = 5
        body = MagicMock()

        def make_foo(
                foo_size: int, foo_next_foo: Optional[Callable[..., Awaitable]]
        ) -> Callable[..., Awaitable]:
            event = asyncio.Event()

            @rate(size=foo_size)
            async def foo():
                while (not event.is_set()) and (foo.rate.async_waiters != 1):
                    await asyncio.sleep(0)

                body(foo_size)
                event.set()

                if foo_next_foo is not None:
                    await foo_next_foo()

            return foo

        next_foo: Optional[Callable[..., Awaitable]] = None
        for size in range(1, depth):
            next_foo = make_foo(size, next_foo)

        await gather(*[next_foo() for _ in range(depth)])

        body.assert_has_calls([
            call(repeat)
            for repeat in range(1, depth)
            for _ in range(repeat)
        ], any_order=True)

    @patch('atools.rate_decorator.async_sleep')
    @patch('atools.rate_decorator.time')
    @async_test_case
    async def test_window_size_limits_async_concurrency_to_size(
            self,
            m_time: MagicMock,
            m_async_sleep: MagicMock,
    ) -> None:
        m_time.return_value = 0.0
        wake = asyncio.Event()
        m_async_sleep.side_effect = lambda *args, **kwargs: wake.wait()

        body = MagicMock()

        duration = timedelta(days=365)

        @rate(size=1, duration=duration)
        async def foo() -> None:
            body(m_time())

        await foo()

        task = asyncio.ensure_future(foo())

        while foo.rate.async_waiters != 1:
            await asyncio.sleep(0)

        m_time.return_value = duration.total_seconds()
        wake.set()
        await task

        m_async_sleep.assert_called_with(duration.total_seconds())

        body.assert_has_calls([call(0.0), call(duration.total_seconds())], any_order=False)

    @patch('atools.rate_decorator.sync_sleep')
    @patch('atools.rate_decorator.time')
    def test_window_size_limits_sync_concurrency_to_size(
            self,
            m_time: MagicMock,
            m_sync_sleep: MagicMock,
    ) -> None:
        m_time.return_value = 0.0
        wake = threading.Event()
        m_sync_sleep.side_effect = lambda *args, **kwargs: wake.wait()

        body = MagicMock()

        duration = timedelta(days=365)

        @rate(size=1, duration=duration, thread_safe=True)
        def foo() -> None:
            body(m_time())

        foo()

        with ThreadPoolExecutor() as executor:
            executor.submit(foo)

            while foo.rate.sync_waiters != 1:
                pass

            m_time.return_value = duration.total_seconds()
            wake.set()

        m_sync_sleep.assert_called_with(duration.total_seconds())

        body.assert_has_calls([call(0.0), call(duration.total_seconds())], any_order=False)


if __name__ == '__main__':
    unittest.main(verbosity=2)
