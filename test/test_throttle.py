import asyncio
import functools
import inspect
import unittest.mock
import pytest

import atools

inspect.getmodule(atools.Throttle)


@pytest.fixture
def m_asyncio() -> unittest.mock.MagicMock:
    with unittest.mock.patch.object(inspect.getmodule(atools.Throttle), 'asyncio', autospec=True) as m_asyncio:
        yield m_asyncio


@pytest.fixture
def m_time() -> unittest.mock.MagicMock:
    with unittest.mock.patch.object(inspect.getmodule(atools.Throttle), 'time', autospec=True) as m_time:
        yield m_time


def test_sleeps_when_max_through_exceeded_in_window(
    m_asyncio: unittest.mock.MagicMock,
    m_time: unittest.mock.MagicMock,
) -> None:

    @atools.Throttle(max_window=1, window=1.0)
    async def async_foo():
        ...

    @atools.Throttle(max_window=1, window=1.0)
    def multi_foo():
        ...

    for foo, sleep in [
        (lambda: asyncio.run(async_foo()), m_asyncio.sleep),
        (multi_foo, m_time.sleep),
    ]:
        m_time.time.return_value = 0.0

        foo()
        sleep.assert_not_called()
        m_time.reset_mock()

        foo()
        sleep.assert_called_once_with(1.0)
        m_time.reset_mock()

        foo()
        foo()
        sleep.assert_has_calls([unittest.mock.call(2.0), unittest.mock.call(3.0)])
        m_time.reset_mock()


def test_multiple_through_starts_at_one(m_time: unittest.mock.MagicMock) -> None:

    @atools.Throttle(max_window=4, window=1.0)
    def foo():
        ...

    m_time.time.return_value = 0.0
    foo()
    foo()
    m_time.sleep.assert_called_once_with(1.0)
    m_time.reset_mock()
