from asyncio import get_event_loop
from atools import memoize
from atools.util import seconds
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
            self.assertNotIn(1, calls)
            calls.add(1)

        foo()
        foo()
        self.assertIn(1, calls)

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
            self.assertNotIn(1, calls)
            calls.add(1)
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
            self.assertNotIn(1, calls)
            calls.add(1)
            raise FooException()

        for _ in range(2):
            with self.assertRaises(FooException):
                self.loop.run_until_complete(foo(1))

    @patch('atools.memoize_decorator.time')
    def test_expire(self, m_time: MagicMock) -> None:
        calls = set()

        @memoize(expire='1000000s')
        def foo() -> None:
            self.assertNotIn(None, calls)
            calls.add(None)

        m_time.return_value = 0.0
        foo()
        self.assertEqual({None}, calls)

        m_time.return_value = seconds('999999s')
        foo()
        self.assertEqual({None}, calls)

        calls.remove(None)
        m_time.return_value = seconds('1000001s')
        foo()
        self.assertEqual({None}, calls)


if __name__ == '__main__':
    unittest.main()
