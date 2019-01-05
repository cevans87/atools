from asyncio import gather, get_event_loop
from atools import async_test_case, memoize
from atools.util import duration
from typing import List
import unittest
from unittest.mock import call, MagicMock, patch


@async_test_case
class TestMemoize(unittest.TestCase):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.loop = get_event_loop()

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

    def test_size(self) -> None:
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

        @memoize(expire='24h')
        def foo() -> None:
            body()

        m_time.return_value = 0.0
        foo()
        m_time.return_value = duration('23h59m59s')
        foo()
        body.assert_called_once()
        body.reset_mock()

        m_time.return_value = duration('24h1s')
        foo()
        body.assert_called_once()

    @patch('atools.memoize_decorator.time')
    def test_expire_old_call(self, m_time: MagicMock) -> None:
        body = MagicMock()

        @memoize(expire='24h')
        def foo(bar: int) -> None:
            body(bar)

        m_time.return_value = duration('0s')
        foo(1)
        body.assert_called_once_with(1)
        self.assertEqual(len(foo.memoize), 1)
        body.reset_mock()

        m_time.return_value = duration('24h1s')
        foo(2)
        body.assert_called_once_with(2)
        self.assertEqual(len(foo.memoize), 1)

    @patch('atools.memoize_decorator.time')
    def test_expire_old_item_does_not_expire_new(self, m_time: MagicMock) -> None:
        body = MagicMock()

        @memoize(expire='24h')
        def foo() -> None:
            body()

        m_time.return_value = duration('0s')
        foo()
        body.assert_called_once_with()
        body.reset_mock()

        m_time.return_value = duration('24h1s')
        foo()
        body.assert_called_once_with()
        body.reset_mock()

        m_time.return_value = duration('24h2s')
        foo()
        body.assert_not_called()

    @patch('atools.memoize_decorator.time')
    def test_expire_head_of_line_refresh_does_not_stop_eviction(self, m_time: MagicMock) -> None:
        body = MagicMock()

        @memoize(expire='24h')
        def foo(bar: int) -> None:
            body(bar)

        m_time.return_value = duration('0s')
        foo(1)
        foo(2)
        body.assert_has_calls([call(1), call(2)], any_order=False)
        self.assertEqual(len(foo.memoize), 2)
        body.reset_mock()

        m_time.return_value = duration('24h1s')
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
        for expire in ['-1s', '0s', -1, 0, -1.0, 0.0]:
            with self.assertRaises(AssertionError):
                @memoize(expire=expire)
                def foo() -> None:
                    ...

    def test_args_overlaps_kwargs_raises(self) -> None:

        @memoize
        def foo(_bar: int) -> None:
            ...

        with self.assertRaises(TypeError):
            foo(1, _bar=1)

    def test_pass_unhashable_true_passes_calls(self) -> None:
        body = MagicMock()

        @memoize(pass_unhashable=True)
        def foo(bar: List) -> None:
            body(bar)

        foo([])
        body.assert_called_once_with([])

    def test_pass_unhashable_false_raises(self) -> None:
        @memoize(pass_unhashable=False)
        def foo(_bar: List) -> None:
            ...

        with self.assertRaises(TypeError):
            foo([])

    def test_reset(self) -> None:
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

    # FIXME The following tests do not prove the safety of the 'thread_safe' flag. The difficulty
    #  deterministically producing race conditions spawned the idea of RaceMock to force race
    #  conditions outside a mutex lock. See https://github.com/cevans87/atools/projects/4

    @patch('atools.memoize_decorator.Lock', side_effect=None)
    def test_thread_safe_false_does_not_lock(self, m_lock: MagicMock) -> None:
        @memoize(thread_safe=False)
        def foo() -> None:
            ...

        foo()
        m_lock.assert_not_called()

    @patch('atools.memoize_decorator.Lock', side_effect=None)
    def test_thread_safe_true_locks(self, m_lock: MagicMock) -> None:
        @memoize(thread_safe=True)
        def foo() -> None:
            ...

        foo()
        m_lock.assert_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
