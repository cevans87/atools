from asyncio import (
    coroutine, ensure_future, Event, gather, get_event_loop, new_event_loop, set_event_loop
)
from atools import memoize
import atools._memoize_decorator as test_module
from datetime import timedelta
from pathlib import Path, PosixPath
import pytest
from sqlite3 import connect
from tempfile import NamedTemporaryFile
from typing import Callable, FrozenSet, Hashable, Iterable, Tuple
from unittest.mock import call, MagicMock, patch
from weakref import ref


def get_table_len(db_path: Path) -> int:
    db = connect(f'{db_path}')
    # noinspection SqlResolve
    return len(db.execute("SELECT name FROM sqlite_master where type='table'").fetchall())


@pytest.fixture
def async_lock() -> MagicMock:
    with patch.object(test_module, 'AsyncLock', side_effect=None) as async_lock:
        yield async_lock


@pytest.fixture
def db_path() -> Path:
    with NamedTemporaryFile() as f:
        yield Path(f.name)


@pytest.fixture
def sync_lock() -> MagicMock:
    with patch.object(test_module, 'SyncLock', side_effect=None) as sync_lock:
        yield sync_lock


@pytest.fixture
def time() -> MagicMock:
    with patch.object(test_module, 'time') as time:
        yield time


def test_zero_args() -> None:
    body = MagicMock()

    @memoize
    def foo() -> None:
        body()

    foo()
    foo()
    assert body.call_count == 1


def test_none_arg() -> None:
    body = MagicMock()

    @memoize
    def foo(_bar) -> None:
        body()

    foo(None)
    foo(None)
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
    time.return_value = timedelta(hours=24, microseconds=-1).total_seconds()
    foo()
    body.assert_called_once()
    body.reset_mock()

    time.return_value = timedelta(hours=24, microseconds=1).total_seconds()
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

    time.return_value = timedelta(hours=24, microseconds=1).total_seconds()
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
    assert body.call_count == 1

    time.return_value = timedelta(hours=24, seconds=1).total_seconds()
    foo()
    assert body.call_count == 2

    time.return_value = timedelta(hours=24, seconds=2).total_seconds()
    foo()
    assert body.call_count == 2


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

    memoize.reset_all()
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

    memoize.reset_all()
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
    # FIXME there's a race condition here. Garbage collector may not have cleaned up f yet
    assert r() is None


def test_memoize_class_preserves_doc() -> None:

    @memoize
    class Foo:
        """Foo doc"""
        
    assert Foo.__doc__ == "Foo doc"


def test_keygen_overrides_default() -> None:
    body = MagicMock()

    @memoize(keygen=lambda bar, baz: (bar,))
    def foo(bar: int, baz: int) -> int:
        body(bar, baz)
        
        return bar + baz

    assert foo(2, 2) == 4
    # noinspection PyArgumentEqualDefault
    assert foo(2, 200) == 4
    body.assert_called_once_with(2, 2)


@pytest.mark.asyncio
async def test_keygen_awaits_awaitable_parts() -> None:
    
    key_part_body = MagicMock()

    async def key_part(bar: int, baz: int) -> Tuple[Hashable, ...]:
        key_part_body(bar, baz)
        
        return bar,

    body = MagicMock()

    @memoize(keygen=lambda bar, baz: (key_part(bar, baz),))
    async def foo(bar: int, baz: int) -> int:
        body(bar, baz)

        return bar + baz

    assert await foo(2, 2) == 4
    # noinspection PyArgumentEqualDefault
    assert await foo(2, 200) == 4
    body.assert_called_once_with(2, 2)
    
    assert key_part_body.call_count == 2
    key_part_body.assert_has_calls(
        [call(2, 2), call(2, 200)]
    )


def test_db_creates_table_for_each_decorator(db_path: Path) -> None:
    
    assert get_table_len(db_path) == 0

    @memoize(db_path=db_path)
    def foo() -> None:
        ...

    assert get_table_len(db_path) == 1

    @memoize(db_path=db_path)
    def bar() -> None:
        ...

    assert get_table_len(db_path) == 2


def test_db_reloads_values_from_disk(db_path: Path) -> None:
    body = MagicMock()
    
    def foo() -> None:

        @memoize(db_path=db_path)
        def foo_inner() -> None:
            body()

        foo_inner()

    foo()
    foo()
    
    assert body.call_count == 1


def test_reset_removes_values_on_disk(db_path: Path) -> None:
    body = MagicMock()

    def foo() -> None:
        @memoize(db_path=db_path)
        def foo_inner() -> None:
            body()

        foo_inner()
        foo_inner.memoize.reset()

    foo()
    foo()

    assert body.call_count == 2


def test_db_expires_memo(db_path: Path, time: MagicMock) -> None:
    body = MagicMock()

    def foo() -> None:
        @memoize(db_path=db_path, duration=timedelta(days=1))
        def foo_inner() -> None:
            body()

        foo_inner()

    time.return_value = 0.0
    foo()
    time.return_value = timedelta(hours=24, seconds=1).total_seconds()
    foo()

    assert body.call_count == 2


def test_db_memoizes_multiple_values(db_path: Path) -> None:
    body = MagicMock()

    def get_foo() -> Callable[[int], None]:
        @memoize(db_path=db_path)
        def _foo(_i: int) -> None:
            body(_i)

        return _foo

    foo = get_foo()
    for i in range(10):
        foo(i)
    assert len(foo.memoize) == 10
    
    foo = get_foo()
    assert len(foo.memoize) == 10


def test_db_with_size_expires_lru(db_path: Path) -> None:
    body = MagicMock()

    def foo(it: Iterable[int]) -> None:
        @memoize(db_path=db_path, size=5)
        def foo_inner(_i: int) -> None:
            body(_i)

        for i in it:
            foo_inner(i)

    foo(range(10))
    assert body.call_count == 10
    foo(reversed(range(10)))
    assert body.call_count == 15
    
    
def test_db_with_duration_expires_stale_values(
        db_path: Path,
        time: MagicMock,
) -> None:
    body = MagicMock()

    def foo(it: Iterable[int]) -> None:
        @memoize(db_path=db_path, duration=timedelta(hours=1))
        def foo_inner(_i: int) -> None:
            body(_i)

        for i in it:
            foo_inner(i)

    time.return_value = 0.0
    foo(range(10))
    assert body.call_count == 10

    time.return_value = timedelta(hours=1, microseconds=-1).total_seconds()
    foo(range(10))
    assert body.call_count == 10

    time.return_value = timedelta(hours=1, microseconds=1).total_seconds()
    foo(range(10))
    assert body.call_count == 20


def test_db_memoizes_frozenset(db_path: Path) -> None:
    body = MagicMock()

    def foo() -> FrozenSet[int]:
        @memoize(db_path=db_path)
        def foo_inner() -> FrozenSet[int]:
            body()
            return frozenset({1, 2, 3})

        return foo_inner()

    assert foo() == frozenset({1, 2, 3})
    assert body.call_count == 1

    assert foo() == frozenset({1, 2, 3})
    assert body.call_count == 1


def test_sync_reset_call_resets_one() -> None:
    body = MagicMock()

    @memoize
    def foo(bar: int) -> None:
        body(bar)

    for i in range(10):
        foo(i)
    assert body.call_count == 10

    foo.memoize.reset_call(5)
    for i in range(10):
        foo(i)
    assert body.call_count == 11


def test_reset_call_before_expire_resets_one(time: MagicMock) -> None:
    body = MagicMock()

    @memoize(duration=timedelta(days=1))
    def foo(bar: int) -> None:
        body(bar)

    time.return_value = 0.0
    foo(0)
    foo(0)
    assert body.call_count == 1

    foo.memoize.reset_call(0)
    foo(0)
    foo(0)
    assert body.call_count == 2


@pytest.mark.asyncio
async def test_async_reset_call_resets_call() -> None:
    body = MagicMock()

    @memoize
    async def foo(bar: int) -> None:
        body(bar)

    for i in range(10):
        await foo(i)
    assert body.call_count == 10

    await foo.memoize.reset_call(5)
    for i in range(10):
        await foo(i)
    assert body.call_count == 11


def test_reset_call_with_db_resets_call(db_path: Path) -> None:
    body = MagicMock()

    def get_foo() -> Callable[[int], None]:
        @memoize(db_path=db_path)
        def foo(_i: int) -> None:
            body(_i)

        return foo

    foo = get_foo()
    for i in range(10):
        foo(i)
    assert body.call_count == 10

    foo = get_foo()
    foo.memoize.reset_call(5)
    for i in range(10):
        foo(i)
    assert body.call_count == 11


@pytest.mark.asyncio
async def test_async_keygen_can_return_non_tuple() -> None:
    body = MagicMock()

    def keygen() -> int:
        return 1

    @memoize(keygen=lambda: keygen())
    async def foo() -> None:
        body()

    await foo()
    await foo()
    assert body.call_count == 1


def test_db_can_return_type_of_callers_globals(db_path: Path) -> None:

    @memoize(db_path=db_path)
    def foo():
        return PosixPath.cwd()

    assert foo() == PosixPath.cwd()
    assert isinstance(foo(), PosixPath)


def test_memoized_function_is_deletable() -> None:
    def get_foo() -> Callable[[], None]:
        @memoize
        def _foo() -> None:
            ...

        return _foo

    foo = get_foo()
    r = ref(foo)
    assert r() is not None
    del foo
    # FIXME there's a race condition here. Garbage collector may not have cleaned up foo yet
    assert r() is None


def test_keygen_works_with_default_kwargs() -> None:
    @memoize(keygen=lambda bar: bar)
    def foo(bar=1) -> None:
        ...

    foo()


def test_sync_memo_lifetime_is_lte_arg_with_default_object_hash() -> None:
    # Inherits object.__hash__
    class Bar:
        ...

    @memoize
    def foo(_bar: Bar) -> None:
        pass

    bar = Bar()
    foo(bar)
    assert len(foo.memoize) == 1

    del bar
    assert len(foo.memoize) == 0


@pytest.mark.asyncio
async def test_async_memo_lifetime_is_lte_arg_with_default_object_hash() -> None:
    # Inherits object.__hash__
    class Bar:
        ...

    @memoize
    async def foo(_bar: Bar) -> None:
        pass

    bar = Bar()
    await foo(bar)
    assert len(foo.memoize) == 1

    del bar
    assert len(foo.memoize) == 0


def test_sync_memo_lifetime_is_lte_keygen_part_with_default_default_hash() -> None:
    # Inherits object.__hash__
    class Bar:
        ...

    @memoize(keygen=lambda _bar: _bar)
    def foo(_bar: Bar) -> None:
        pass

    bar = Bar()
    foo(bar)
    assert len(foo.memoize) == 1
    del bar
    assert len(foo.memoize) == 0


@pytest.mark.asyncio
async def test_async_memo_lifetime_is_lte_keygen_part_with_default_default_hash() -> None:
    # Inherits object.__hash__
    class Bar:
        ...

    @memoize(keygen=lambda _bar: _bar)
    async def foo(_bar: Bar) -> None:
        pass

    bar = Bar()
    await foo(bar)
    assert len(foo.memoize) == 1
    del bar
    assert len(foo.memoize) == 0


def test_sync_memo_lifetime_not_affected_by_arg_with_non_default_hash() -> None:
    class Bar:
        def __hash__(self) -> int:
            return hash('Bar')

    @memoize
    def foo(_bar: Bar) -> None:
        pass

    bar = Bar()
    foo(bar)
    assert len(foo.memoize) == 1
    del bar
    assert len(foo.memoize) == 1


@pytest.mark.asyncio
async def test_async_memo_lifetime_not_affected_by_arg_with_non_default_hash() -> None:
    class Bar:
        def __hash__(self) -> int:
            return hash('Bar')

    @memoize
    async def foo(_bar: Bar) -> None:
        pass

    bar = Bar()
    await foo(bar)
    assert len(foo.memoize) == 1
    del bar
    assert len(foo.memoize) == 1


def test_sync_memo_lifetime_lte_keygen_part_with_non_default_hash() -> None:
    # Inherits object.__hash__
    class Bar:
        ...

    @memoize(keygen=lambda _bar: '_bar')
    def foo(_bar: Bar) -> None:
        pass

    bar = Bar()
    foo(bar)
    assert len(foo.memoize) == 1
    del bar
    assert len(foo.memoize) == 1


@pytest.mark.asyncio
async def test_async_memo_lifetime_lte_keygen_part_with_non_default_hash() -> None:
    # Inherits object.__hash__
    class Bar:
        ...

    @memoize(keygen=lambda _bar: '_bar')
    async def foo(_bar: Bar) -> None:
        pass

    bar = Bar()
    await foo(bar)
    assert len(foo.memoize) == 1
    del bar
    assert len(foo.memoize) == 1
