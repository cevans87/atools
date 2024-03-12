import asyncio
import inspect
import unittest.mock
import pytest

import atools

module = inspect.getmodule(atools.Throttle)


# FIXME: Multi tests are missing. This suite heavily relies upon determining whether coroutines are running vs
#  suspended (via asyncio.eager_task_factory). Ideally, similar functionality exists for threading. Otherwise, we need
#  to find a way to determine that thread execution has reached a certain point. Ideally without mocking synchronization
#  primitives.


@pytest.fixture(autouse=True)
def event_loop() -> asyncio.AbstractEventLoop:
    """All async tests execute eagerly.

    Upon task creation return, we can be sure that the task has gotten to a point that it is either blocked or done.
    """

    eager_loop = asyncio.new_event_loop()
    eager_loop.set_task_factory(asyncio.eager_task_factory)
    yield eager_loop
    eager_loop.close()


@pytest.fixture
def m_asyncio() -> unittest.mock.MagicMock:
    with unittest.mock.patch.object(module.asyncio, 'sleep', autospec=True):
        yield module.asyncio


@pytest.fixture
def m_threading() -> unittest.mock.MagicMock:
    with unittest.mock.patch.object(module, 'threading', autospec=True, wraps=module.threading) as m_threading:
        yield m_threading


@pytest.fixture
def m_time() -> unittest.mock.MagicMock:
    with unittest.mock.patch.object(inspect.getmodule(atools.Throttle), 'time', autospec=True) as m_time:
        yield m_time


@pytest.mark.asyncio
async def test_async_sleeps_when_max_herd_exceeded_in_window(m_asyncio, m_time) -> None:

    @atools.Throttle(max_units=1, window=1.0)
    async def foo():
        ...

    m_time.time.return_value = 0.0
    await foo()
    m_asyncio.sleep.assert_not_called()

    await foo()
    m_asyncio.sleep.assert_called_once_with(1.0)


@pytest.mark.asyncio
@pytest.mark.parametrize('start', [1, 2, 10])
async def test_async_value_starts_at_start(start: int) -> None:
    event = asyncio.Event()
    n_running = 0

    @atools.Throttle(start=start)
    async def foo():
        nonlocal n_running
        n_running += 1
        await event.wait()
        n_running -= 1

    async with asyncio.TaskGroup() as tg:
        for _ in range(start * 2):
            tg.create_task(foo())
        assert n_running == start
        event.set()


@pytest.mark.asyncio
@pytest.mark.parametrize('start', [1, 2, 10])
async def test_exception_cuts_value_in_half(start) -> None:
    event = asyncio.Event()
    fail = True
    n_running = 0

    @atools.Throttle(start=start)
    async def foo():
        nonlocal fail
        if fail:
            raise Exception()

        nonlocal n_running
        n_running += 1
        await event.wait()
        n_running -= 1

    with pytest.raises(Exception):
        await foo()
    fail = False

    async with asyncio.TaskGroup() as tg:
        for _ in range(start * 2):
            tg.create_task(foo())
        assert n_running == start // 2
        event.set()
