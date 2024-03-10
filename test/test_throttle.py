import asyncio
import concurrent.futures
import dataclasses
import functools
import inspect
import threading
import unittest.mock
import pytest
import typing

import atools

module = inspect.getmodule(atools.Throttle)


@pytest.fixture
def m_asyncio() -> unittest.mock.MagicMock:
    with unittest.mock.patch.object(module, 'asyncio', autospec=True) as m_asyncio:
        yield m_asyncio


@pytest.fixture
def m_threading() -> unittest.mock.MagicMock:
    with (
        unittest.mock.patch.object(
            module, 'asyncio.Condition', autospec=True, new_callable=unittest.mock.MagicProxy
        ) as m_condition,
        unittest.mock.patch.object(module, 'asyncio', autospec=True) as m_asyncio
    ):
        m_asyncio.Condition.side_effect = asyncio.Condition
        yield m_asyncio


@pytest.fixture
def m_time() -> unittest.mock.MagicMock:
    with unittest.mock.patch.object(inspect.getmodule(atools.Throttle), 'time', autospec=True) as m_time:
        yield m_time


def test_sleeps_when_max_herd_exceeded_in_window(m_threading, m_time) -> None:

    @atools.Throttle(max_herd=1, window=1.0)
    def foo():
        ...

    m_time.time.return_value = 0.0

    foo()
    m_time.sleep.assert_not_called()

    foo()
    m_time.sleep.assert_called_once_with(1.0)


@pytest.mark.asyncio
async def test_value_starts_at_one() -> None:
    semaphore = asyncio.Semaphore(0)

    @atools.Throttle(max_hold=2)
    async def foo():
        async with semaphore:
            ...
    foos = [asyncio.ensure_future(foo()), asyncio.ensure_future(foo()), asyncio.ensure_future(foo())]
    done, pending = await asyncio.wait(foos, timeout=0.1)
    assert len(semaphore._waiters) == 1
    semaphore.release()

    done, pending = await asyncio.wait(pending, timeout=0.1)
    assert len(semaphore._waiters) == 2
    semaphore.release()
    semaphore.release()

    done, pending = await asyncio.wait(pending, timeout=0.1)
    assert not pending
