from asyncio import gather, get_event_loop
from atools import memoize
from atools.util import duration
import unittest
from unittest.mock import MagicMock, patch


class TestMemoize(unittest.TestCase):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.loop = get_event_loop()

    def test_zero_args(self) -> None:
        calls = set()

        @memoize
        def foo() -> None:
            self.assertNotIn(None, calls)
            calls.add(None)

        foo()
        foo()
        self.assertEqual({None}, calls)

    def test_keyword_same_as_default(self) -> None:
        calls = set()

        @memoize
        def foo(bar: int, baz: int = 1) -> int:
            self.assertNotIn((bar, baz), calls)
            calls.add((bar, baz))
            return bar + baz

        self.assertEqual(foo(1), 2)
        # noinspection PyArgumentEqualDefault
        self.assertEqual(foo(1, baz=1), 2)
        self.assertEqual(calls, {(1, 1)})

    def test_async(self) -> None:
        calls = set()

        @memoize
        async def foo(bar: int, baz: int = 1) -> int:
            self.assertNotIn((bar, baz), calls)
            calls.add((bar, baz))
            return bar + baz

        self.assertEqual(self.loop.run_until_complete(foo(1)), 2)
        # noinspection PyArgumentEqualDefault
        self.assertEqual(self.loop.run_until_complete(foo(1, baz=1)), 2)
        self.assertEqual(calls, {(1, 1)})

    def test_size(self) -> None:
        calls = set()

        @memoize(size=1)
        def foo(bar) -> None:
            self.assertNotIn(bar, calls)
            calls.add(bar)

        foo(0)
        foo(1)
        self.assertEqual({0, 1}, calls)
        calls.remove(0)
        foo(0)
        self.assertEqual({0, 1}, calls)

    def test_sync_exception(self) -> None:
        class FooException(Exception):
            ...

        calls = set()

        @memoize
        def foo() -> None:
            self.assertNotIn(None, calls)
            calls.add(None)
            raise FooException()

        for _ in range(2):
            with self.assertRaises(FooException):
                foo()

    def test_async_exception(self) -> None:
        class FooException(Exception):
            ...

        calls = set()

        @memoize
        async def foo() -> None:
            self.assertNotIn(None, calls)
            calls.add(None)
            raise FooException()

        for _ in range(2):
            with self.assertRaises(FooException):
                self.loop.run_until_complete(foo(1))

    @patch('atools.memoize_decorator.time')
    def test_expire_current_call(self, m_time: MagicMock) -> None:
        calls = set()

        @memoize(expire='24h')
        def foo() -> None:
            self.assertNotIn(None, calls)
            calls.add(None)

        m_time.return_value = 0.0
        foo()
        self.assertEqual({None}, calls)

        calls.remove(None)
        m_time.return_value = duration('23h59m59s')
        foo()
        self.assertEqual(set(), calls)

        m_time.return_value = duration('24h1s')
        foo()
        self.assertEqual({None}, calls)

    @patch('atools.memoize_decorator.time')
    def test_expire_old_call(self, m_time: MagicMock) -> None:
        calls = set()

        @memoize(expire='24h')
        def foo(bar: int) -> None:
            self.assertNotIn(bar, calls)
            calls.add(bar)

        m_time.return_value = 0.0
        foo(1)
        self.assertEqual({1}, calls)

        calls.remove(1)
        m_time.return_value = duration('24h1s')
        foo(2)
        self.assertEqual({2}, calls)

        m_time.return_value = 0.0
        foo(1)
        self.assertEqual({1, 2}, calls)

    def test_async_thundering_herd(self) -> None:
        calls = set()

        @memoize
        async def foo() -> None:
            self.assertNotIn(None, calls)
            calls.add(None)

        self.loop.run_until_complete(gather(foo(), foo()))
        self.assertEqual({None}, calls)

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


if __name__ == '__main__':
    unittest.main()
