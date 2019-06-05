from asyncio import (
    coroutine, ensure_future, Event, gather, get_event_loop, new_event_loop, set_event_loop
)
from atools import async_test_case, memoize
from datetime import timedelta
import unittest
from unittest.mock import call, MagicMock, patch


@async_test_case
class TestMemoize(unittest.TestCase):
    
    def test_zero_args(self) -> None:
        body = MagicMock()

        @memoize
        def foo() -> None:
            body()

        foo()
        foo()
        body.assert_called_once()

    def test_class_function(self) -> None:
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

    def test_keyword_same_as_default(self) -> None:
        body = MagicMock()

        @memoize
        def foo(bar: int, baz: int = 1) -> int:
            body(bar, baz)

            return bar + baz

        self.assertEqual(foo(1), 2)
        # noinspection PyArgumentEqualDefault
        self.assertEqual(foo(1, baz=1), 2)
        body.assert_called_once_with(1, 1)

    async def test_async(self) -> None:
        body = MagicMock()

        @memoize
        async def foo(bar: int, baz: int = 1) -> int:
            body(bar, baz)

            return bar + baz

        self.assertEqual(await foo(1), 2)
        # noinspection PyArgumentEqualDefault
        self.assertEqual(await foo(1, baz=1), 2)
        body.assert_called_once_with(1, 1)

    def test_sync_size(self) -> None:
        body = MagicMock()

        @memoize(size=1)
        def foo(bar) -> None:
            body(bar)

        foo(0)
        self.assertEqual(len(foo.memoize), 1)
        foo(1)
        self.assertEqual(len(foo.memoize), 1)
        body.assert_has_calls([call(0), call(1)], any_order=False)
        body.reset_mock()
        foo(0)
        self.assertEqual(len(foo.memoize), 1)
        body.assert_called_once_with(0)

    async def test_async_size(self) -> None:
        body = MagicMock()

        @memoize(size=1)
        async def foo(bar) -> None:
            body(bar)

        await foo(0)
        self.assertEqual(len(foo.memoize), 1)
        await foo(1)
        self.assertEqual(len(foo.memoize), 1)
        body.assert_has_calls([call(0), call(1)], any_order=False)
        body.reset_mock()
        await foo(0)
        self.assertEqual(len(foo.memoize), 1)
        body.assert_called_once_with(0)

    def test_sync_exception(self) -> None:
        class FooException(Exception):
            ...

        body = MagicMock()

        @memoize
        def foo() -> None:
            body()
            raise FooException()

        for _ in range(2):
            with self.assertRaises(FooException):
                foo()

        body.assert_called_once()

    async def test_async_exception(self) -> None:
        class FooException(Exception):
            ...

        body = MagicMock()

        @memoize
        async def foo() -> None:
            body()
            raise FooException()

        for _ in range(2):
            with self.assertRaises(FooException):
                await foo()

        body.assert_called_once()

    @patch('atools.memoize_decorator.time')
    def test_expire_current_call(self, m_time: MagicMock) -> None:
        body = MagicMock()

        @memoize(duration=timedelta(days=1))
        def foo() -> None:
            body()

        m_time.return_value = 0.0
        foo()
        m_time.return_value = timedelta(hours=23, minutes=59, seconds=59).total_seconds()
        foo()
        body.assert_called_once()
        body.reset_mock()

        m_time.return_value = timedelta(hours=24, seconds=1).total_seconds()
        foo()
        body.assert_called_once()

    @patch('atools.memoize_decorator.time')
    def test_expire_old_call(self, m_time: MagicMock) -> None:
        body = MagicMock()

        @memoize(duration=timedelta(days=1))
        def foo(bar: int) -> None:
            body(bar)

        m_time.return_value = 0.0
        foo(1)
        body.assert_called_once_with(1)
        self.assertEqual(len(foo.memoize), 1)
        body.reset_mock()

        m_time.return_value = timedelta(hours=24, seconds=1).total_seconds()
        foo(2)
        body.assert_called_once_with(2)
        self.assertEqual(len(foo.memoize), 1)

    @patch('atools.memoize_decorator.time')
    def test_expire_old_item_does_not_expire_new(self, m_time: MagicMock) -> None:
        body = MagicMock()

        @memoize(duration=timedelta(days=1))
        def foo() -> None:
            body()

        m_time.return_value = 0.0
        foo()
        body.assert_called_once_with()
        body.reset_mock()

        m_time.return_value = timedelta(hours=24, seconds=1).total_seconds()
        foo()
        body.assert_called_once_with()
        body.reset_mock()

        m_time.return_value = timedelta(hours=24, seconds=2).total_seconds()
        foo()
        body.assert_not_called()

    @patch('atools.memoize_decorator.time')
    def test_expire_head_of_line_refresh_does_not_stop_eviction(self, m_time: MagicMock) -> None:
        body = MagicMock()

        @memoize(duration=timedelta(hours=24))
        def foo(bar: int) -> None:
            body(bar)

        m_time.return_value = 0.0
        foo(1)
        foo(2)
        body.assert_has_calls([call(1), call(2)], any_order=False)
        self.assertEqual(len(foo.memoize), 2)
        body.reset_mock()

        m_time.return_value = timedelta(hours=24, seconds=1).total_seconds()
        foo(1)
        body.assert_called_once_with(1)
        self.assertEqual(len(foo.memoize), 1)

    async def test_async_thundering_herd(self) -> None:
        body = MagicMock()

        @memoize
        async def foo() -> None:
            body()

        await gather(foo(), foo())
        body.assert_called_once()

    def test_size_le_zero_raises(self) -> None:
        for size in [-1, 0]:
            with self.assertRaises(AssertionError):
                @memoize(size=size)
                def foo() -> None:
                    ...

    def test_expire_le_zero_raises(self) -> None:
        for duration in [timedelta(seconds=-1), timedelta(seconds=0), -1, 0, -1.0, 0.0]:
            with self.assertRaises(AssertionError):
                @memoize(duration=duration)
                def foo() -> None:
                    ...

    def test_args_overlaps_kwargs_raises(self) -> None:

        @memoize
        def foo(_bar: int) -> None:
            ...

        with self.assertRaises(TypeError):
            foo(1, _bar=1)

    def test_sync_reset(self) -> None:
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

    async def test_async_reset(self) -> None:
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

    def test_with_property(self) -> None:
        body = MagicMock()

        class Foo:
            @property
            @memoize
            def bar(self) -> int:
                body(self)

                return 1

        a = Foo()
        self.assertEqual(a.bar, 1)
        body.assert_called_once_with(a)

        b = Foo()
        body.reset_mock()
        self.assertEqual(a.bar, 1)
        self.assertEqual(b.bar, 1)
        body.assert_called_once_with(b)

    @patch('atools.memoize_decorator.LockSync', side_effect=None)
    def test_sync_locks_sync(self, m_lock_sync: MagicMock) -> None:
        @memoize
        def foo() -> None:
            ...

        foo()
        m_lock_sync.assert_called()

    @patch('atools.memoize_decorator.LockSync', side_effect=None)
    @async_test_case
    async def test_async_does_not_lock_sync(self, m_lock_sync: MagicMock) -> None:
        @memoize
        async def foo() -> None:
            ...

        await foo()
        m_lock_sync.assert_not_called()

    @patch('atools.memoize_decorator.LockAsync', side_effect=None)
    @async_test_case
    async def test_async_locks_async(self, m_lock_async: MagicMock) -> None:
        m_lock_async_context = m_lock_async.return_value = MagicMock()
        type(m_lock_async_context).__aenter__ = \
            coroutine(lambda *args, **kwargs: m_lock_async_context)
        type(m_lock_async_context).__aexit__ = coroutine(lambda *args, **kwargs: None)

        @memoize
        async def foo() -> None:
            ...

        await foo()
        m_lock_async.assert_called()

    @patch('atools.memoize_decorator.LockAsync', side_effect=None)
    def test_sync_does_not_lock_async(self, m_lock_async: MagicMock) -> None:
        m_lock_async_context = m_lock_async.return_value = MagicMock()
        type(m_lock_async_context).__aenter__ = \
            coroutine(lambda *args, **kwargs: m_lock_async_context)
        type(m_lock_async_context).__aexit__ = coroutine(lambda *args, **kwargs: None)

        @memoize
        def foo() -> None:
            ...

        foo()
        m_lock_async.assert_not_called()

    def test_async_no_event_loop_does_not_raise(self) -> None:
        # Show that we decorate without having an active event loop
        # noinspection PyTypeChecker
        set_event_loop(None)
        try:
            with self.assertRaises(RuntimeError):
                self.assertIsNone(get_event_loop())

            @memoize
            async def foo() -> None:
                ...
        finally:
            set_event_loop(new_event_loop())

    def test_memoizes_class(self) -> None:
        body = MagicMock()

        class Bar:
            ...

        @memoize
        class Foo(Bar):
            def __init__(self, foo) -> None:
                body(foo)

        self.assertIs(Foo(0), Foo(0))
        body.assert_called_once_with(0)
        self.assertIsNot(Foo(0), Foo(1))

    def test_memoizes_class_with_metaclass(self) -> None:
        body = MagicMock()

        class FooMeta(type):
            pass

        @memoize
        class Foo(metaclass=FooMeta):
            def __init__(self, foo) -> None:
                body(foo)

        self.assertIs(Foo(0), Foo(0))
        body.assert_called_once_with(0)
        self.assertIsNot(Foo(0), Foo(1))

    def test_reset_all_resets_class_decorators(self) -> None:
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

    def test_reset_all_resets_function_decorators(self) -> None:
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

    async def test_async_herd_waits_for_return(self) -> None:
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

        self.assertEqual(foo_a, foo_b)


if __name__ == '__main__':
    unittest.main(verbosity=2)
