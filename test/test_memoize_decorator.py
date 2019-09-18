from asyncio import (
    coroutine, ensure_future, Event, gather, get_event_loop, new_event_loop, set_event_loop
)
from atools import memoize
from atools.memoize_decorator import reset_all
from datetime import timedelta
import pytest
from unittest.mock import call, MagicMock, patch
from weakref import ref


@pytest.fixture
def time() -> MagicMock:
    with patch('atools.memoize_decorator.time') as time:
        yield time


@pytest.fixture
def sync_lock() -> MagicMock:
    with patch('atools.memoize_decorator.SyncLock', side_effect=None) as sync_lock:
        yield sync_lock

@pytest.fixture
def async_lock() -> MagicMock:
    with patch('atools.memoize_decorator.AsyncLock', side_effect=None) as async_lock:
        yield async_lock


def test_zero_args() -> None:
    body = MagicMock()

    @memoize
    def foo() -> None:
        body()

    foo()
    foo()
    assert body.call_count == 1


def test_class_function() -> None:
    body = MagicMock()

    class Foo:
        @memoize
        def foo(self) -> None:
            body()

    f = Foo()
    f.foo()
    f.foo()
    body.assert_called_once()
    body.reset_mock()

    f = Foo()
    f.foo()
    f.foo()
    body.assert_called_once()


def test_keyword_same_as_default() -> None:
    body = MagicMock()

    @memoize
    def foo(bar: int, baz: int = 1) -> int:
        body(bar, baz)

        return bar + baz

    assert foo(1) == 2
    # noinspection PyArgumentEqualDefault
    assert foo(1, baz=1) == 2
    body.assert_called_once_with(1, 1)


@pytest.mark.asyncio
async def test_async() -> None:
    body = MagicMock()

    @memoize
    async def foo(bar: int, baz: int = 1) -> int:
        body(bar, baz)

        return bar + baz

    assert await foo(1) == 2
    # noinspection PyArgumentEqualDefault
    assert await foo(1, baz=1) == 2
    body.assert_called_once_with(1, 1)


def test_sync_size() -> None:
    body = MagicMock()

    @memoize(size=1)
    def foo(bar) -> None:
        body(bar)

    foo(0)
    assert len(foo.memoize) == 1
    foo(1)
    assert len(foo.memoize) == 1
    body.assert_has_calls([call(0), call(1)], any_order=False)
    body.reset_mock()
    foo(0)
    assert len(foo.memoize) == 1
    body.assert_called_once_with(0)


@pytest.mark.asyncio
async def test_async_size() -> None:
    body = MagicMock()

    @memoize(size=1)
    async def foo(bar) -> None:
        body(bar)

    await foo(0)
    assert len(foo.memoize) == 1
    await foo(1)
    assert len(foo.memoize) == 1
    body.assert_has_calls([call(0), call(1)], any_order=False)
    body.reset_mock()
    await foo(0)
    assert len(foo.memoize) == 1
    body.assert_called_once_with(0)


def test_sync_exception() -> None:
    class FooException(Exception):
        ...

    body = MagicMock()

    @memoize
    def foo() -> None:
        body()
        raise FooException()

    for _ in range(2):
        try:
            foo()
        except FooException:
            pass
        else:
            pytest.fail()

    body.assert_called_once()


@pytest.mark.asyncio
async def test_async_exception() -> None:
    class FooException(Exception):
        ...

    body = MagicMock()

    @memoize
    async def foo() -> None:
        body()
        raise FooException()

    for _ in range(2):
        try:
            await foo()
        except FooException:
            pass
        else:
            pytest.fail()

    body.assert_called_once()


def test_expire_current_call(time: MagicMock) -> None:
    body = MagicMock()

    @memoize(duration=timedelta(days=1))
    def foo() -> None:
        body()

    time.return_value = 0.0
    foo()
    time.return_value = timedelta(hours=23, minutes=59, seconds=59).total_seconds()
    foo()
    body.assert_called_once()
    body.reset_mock()

    time.return_value = timedelta(hours=24, seconds=1).total_seconds()
    foo()
    body.assert_called_once()


def test_expire_old_call(time: MagicMock) -> None:
    body = MagicMock()

    @memoize(duration=timedelta(days=1))
    def foo(bar: int) -> None:
        body(bar)

    time.return_value = 0.0
    foo(1)
    body.assert_called_once_with(1)
    assert len(foo.memoize) == 1
    body.reset_mock()

    time.return_value = timedelta(hours=24, seconds=1).total_seconds()
    foo(2)
    body.assert_called_once_with(2)
    assert len(foo.memoize) == 1


def test_expire_old_item_does_not_expire_new(time: MagicMock) -> None:
    body = MagicMock()

    @memoize(duration=timedelta(days=1))
    def foo() -> None:
        body()

    time.return_value = 0.0
    foo()
    body.assert_called_once_with()
    body.reset_mock()

    time.return_value = timedelta(hours=24, seconds=1).total_seconds()
    foo()
    body.assert_called_once_with()
    body.reset_mock()

    time.return_value = timedelta(hours=24, seconds=2).total_seconds()
    foo()
    body.assert_not_called()


def test_expire_head_of_line_refresh_does_not_stop_eviction(time: MagicMock) -> None:
    body = MagicMock()

    @memoize(duration=timedelta(hours=24))
    def foo(bar: int) -> None:
        body(bar)

    time.return_value = 0.0
    foo(1)
    foo(2)
    body.assert_has_calls([call(1), call(2)], any_order=False)
    assert len(foo.memoize) == 2
    body.reset_mock()

    time.return_value = timedelta(hours=24, seconds=1).total_seconds()
    foo(1)
    body.assert_called_once_with(1)
    assert len(foo.memoize) == 1


@pytest.mark.asyncio
async def test_async_stops_thundering_herd() -> None:
    body = MagicMock()

    @memoize
    async def foo() -> None:
        body()

    await gather(foo(), foo())
    body.assert_called_once()


def test_size_le_zero_raises() -> None:
    for size in [-1, 0]:
        try:
            @memoize(size=size)
            def foo() -> None:
                ...
        except AssertionError:
            pass
        else:
            pytest.fail()


def test_expire_le_zero_raises() -> None:
    for duration in [timedelta(seconds=-1), timedelta(seconds=0), -1, 0, -1.0, 0.0]:
        try:
            @memoize(duration=duration)
            def foo() -> None:
                ...
        except AssertionError:
            pass
        else:
            pytest.fail()


def test_args_overlaps_kwargs_raises() -> None:

    @memoize
    def foo(_bar: int) -> None:
        ...

    try:
        foo(1, _bar=1)
    except TypeError:
        pass
    else:
        pytest.fail()


def test_sync_reset_clears_cache() -> None:
    body = MagicMock()

    @memoize
    def foo() -> None:
        body()

    foo()
    body.assert_called_once()
    body.reset_mock()

    foo.memoize.reset()
    foo()
    body.assert_called_once()


@pytest.mark.asyncio
async def test_async_reset_clears_cache() -> None:
    body = MagicMock()

    @memoize
    async def foo() -> None:
        body()

    await foo()
    body.assert_called_once()
    body.reset_mock()

    foo.memoize.reset()
    await foo()
    body.assert_called_once()


def test_works_with_property() -> None:
    body = MagicMock()

    class Foo:
        @property
        @memoize
        def bar(self) -> int:
            body(self)

            return 1

    a = Foo()
    assert a.bar == 1
    body.assert_called_once_with(a)

    b = Foo()
    body.reset_mock()
    assert b.bar == 1
    assert b.bar == 1  # yes, we meant to do this twice
    body.assert_called_once_with(b)


def test_sync_locks_sync(sync_lock: MagicMock) -> None:
    @memoize
    def foo() -> None:
        ...

    foo()
    sync_lock.assert_called()


@pytest.mark.asyncio
async def test_async_does_not_sync_lock(sync_lock: MagicMock) -> None:
    @memoize
    async def foo() -> None:
        ...

    await foo()
    sync_lock.assert_not_called()


@pytest.mark.asyncio
async def test_async_locks_async(async_lock: MagicMock) -> None:
    async_lock_context = async_lock.return_value = MagicMock()
    type(async_lock_context).__aenter__ = \
        coroutine(lambda *args, **kwargs: async_lock_context)
    type(async_lock_context).__aexit__ = coroutine(lambda *args, **kwargs: None)

    @memoize
    async def foo() -> None:
        ...

    await foo()
    async_lock.assert_called()


def test_sync_does_not_async_lock(async_lock: MagicMock) -> None:
    async_lock_context = async_lock.return_value = MagicMock()
    type(async_lock_context).__aenter__ = \
        coroutine(lambda *args, **kwargs: async_lock_context)
    type(async_lock_context).__aexit__ = coroutine(lambda *args, **kwargs: None)

    @memoize
    def foo() -> None:
        ...

    foo()
    async_lock.assert_not_called()


def test_async_no_event_loop_does_not_raise() -> None:
    # Show that we decorate without having an active event loop
    # noinspection PyTypeChecker
    set_event_loop(None)
    try:
        try:
            get_event_loop()
        except RuntimeError:
            pass
        else:
            pytest.fail()

        @memoize
        async def foo() -> None:
            ...
    finally:
        set_event_loop(new_event_loop())


def test_memoizes_class() -> None:
    body = MagicMock()

    class Bar:
        ...

    @memoize
    class Foo(Bar):
        def __init__(self, foo) -> None:
            body(foo)

    assert Foo(0) is Foo(0)
    body.assert_called_once_with(0)
    assert Foo(0) is not Foo(1)


def test_memoizes_class_with_metaclass() -> None:
    body = MagicMock()

    class FooMeta(type):
        pass

    @memoize
    class Foo(metaclass=FooMeta):
        def __init__(self, foo) -> None:
            body(foo)

    assert Foo(0) is Foo(0)
    body.assert_called_once_with(0)
    assert Foo(0) is not Foo(1)


def test_reset_all_resets_class_decorators() -> None:
    foo_body = MagicMock()
    bar_body = MagicMock()

    @memoize
    class Foo:
        def __init__(self) -> None:
            foo_body()

    @memoize
    class Bar:
        def __init__(self) -> None:
            bar_body()

    Foo()
    foo_body.assert_called_once()
    Bar()
    bar_body.assert_called_once()

    reset_all()
    foo_body.reset_mock()
    bar_body.reset_mock()

    Foo()
    foo_body.assert_called_once()
    Bar()
    bar_body.assert_called_once()


def test_reset_all_resets_function_decorators() -> None:
    foo_body = MagicMock()
    bar_body = MagicMock()

    @memoize
    def foo() -> None:
        foo_body()

    @memoize
    def bar() -> None:
        bar_body()

    foo()
    foo_body.assert_called_once()
    bar()
    bar_body.assert_called_once()

    reset_all()
    foo_body.reset_mock()
    bar_body.reset_mock()

    foo()
    foo_body.assert_called_once()
    bar()
    bar_body.assert_called_once()


@pytest.mark.asyncio
async def test_async_herd_waits_for_return() -> None:
    foo_start_event = Event()
    foo_finish_event = Event()

    @memoize
    async def foo() -> int:
        foo_start_event.set()
        await foo_finish_event.wait()
        return 0

    task_a, task_b = ensure_future(foo()), ensure_future(foo())

    await foo_start_event.wait()
    foo_finish_event.set()

    foo_a, foo_b = await gather(task_a, task_b)

    assert foo_a == foo_b


@pytest.mark.asyncio
async def test_memoize_does_not_stop_object_cleanup() -> None:
    class Foo:
        pass

    @memoize
    def foo(_: Foo) -> None:
        ...

    f = Foo()
    foo(f)

    r = ref(f)
    assert r() is not None
    del f
    assert r() is None


def test_memoize_class_preserves_doc() -> None:

    @memoize
    class Foo:
        """Foo doc"""
        
    assert Foo.__doc__ == "Foo doc"
