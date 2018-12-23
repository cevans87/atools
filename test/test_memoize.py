from asyncio import get_event_loop
from atools import memoize
import unittest


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


if __name__ == '__main__':
    unittest.main()
