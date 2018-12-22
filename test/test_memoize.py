from atools import memoize
import unittest


class TestMemoize(unittest.TestCase):

    def test_keyword_same_as_default(self) -> None:
        calls = set()

        @memoize
        def foo(bar: int, baz: int = 1) -> int:
            self.assertTrue((bar, baz) not in calls)
            calls.add((bar, baz))
            return bar + baz

        self.assertEqual(foo(1), 2)
        # noinspection PyArgumentEqualDefault
        self.assertEqual(foo(1, baz=1), 2)
        self.assertEqual(calls, {(1, 1)})


if __name__ == '__main__':
    unittest.main()
