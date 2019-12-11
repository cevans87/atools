import asyncio
from asyncio import coroutine, Event as AsyncEvent, gather
from atools import rate
from concurrent.futures import ThreadPoolExecutor
import pytest
from threading import Event as SyncEvent
from unittest.mock import MagicMock, patch


@pytest.fixture
def time() -> MagicMock:
    with patch('atools._rate_decorator.time') as time:
        time.return_value = 0
        yield time


@pytest.fixture
def async_sleep() -> MagicMock:
    with patch('atools._rate_decorator.async_sleep') as async_sleep:
        yield async_sleep


@pytest.fixture
def sync_sleep() -> MagicMock:
    with patch('atools._rate_decorator.sync_sleep') as sync_sleep:
        yield sync_sleep


def test_size_le_0_fails_assert() -> None:
    for size in [-1, 0]:
        try:
            @rate(size=size)
            def foo() -> None:
                ...
        except AssertionError:
            pass
        else:
            pytest.fail()


def test_size_limits_sync_concurrency_to_size(time: MagicMock) -> None:
    sync_event_0 = SyncEvent()
    sync_event_1 = SyncEvent()
    
    @rate(size=1)
    def foo():
        sync_event_0.set()
        assert sync_event_1.wait()

    with ThreadPoolExecutor() as executor:
        executor.submit(foo)
        executor.submit(foo)

        assert sync_event_0.wait(10)
        assert foo.rate.running == 1
        sync_event_1.set()
        
    assert foo.rate.running == 0


@pytest.mark.asyncio
async def test_size_limits_async_concurrency_to_size(time: MagicMock) -> None:
    async_event_0 = AsyncEvent()
    async_event_1 = AsyncEvent()

    @rate(size=1)
    async def foo():
        async_event_0.set()
        assert await async_event_1.wait()

    fut_0 = asyncio.ensure_future(foo())
    fut_1 = asyncio.ensure_future(foo())

    assert await asyncio.wait_for(async_event_0.wait(), 10)
    assert foo.rate.running == 1
    async_event_1.set()
    
    await asyncio.gather(fut_0, fut_1)

    assert foo.rate.running == 0


def test_duration_causes_sync_waiter_to_sleep(sync_sleep: MagicMock, time: MagicMock) -> None:

    @rate(size=1, duration=10)
    def foo():
        ...

    with ThreadPoolExecutor() as executor:
        executor.submit(foo)
        executor.submit(foo)

    sync_sleep.assert_called_once_with(10)


@pytest.mark.asyncio
async def test_duration_causes_async_waiter_to_sleep(
        async_sleep: MagicMock, time: MagicMock
) -> None:
    async_sleep.side_effect = coroutine(lambda *_: None)

    @rate(size=1, duration=10)
    async def foo():
        ...

    await gather(foo(), foo())

    async_sleep.assert_called_once_with(10)
