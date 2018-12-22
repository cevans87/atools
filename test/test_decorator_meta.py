from typing import Any
import unittest

from decorator_meta import DecoratorMeta


class FooDecorator(metaclass=DecoratorMeta):
    def __init__(self, fn, *, bar='baz') -> None:
        self.fn = fn
        self.bar = bar
        self.call_count = 0

    def __call__(self, *args, **kwargs) -> Any:
        self.call_count += 1
        return self.fn(*args, **kwargs)


class TestDecoratorMeta(unittest.TestCase):
    def test_un_parameterized(self):
        @FooDecorator
        def foo():
            ...

        self.assertIsNotNone(foo.fn)
        self.assertEqual(foo.bar, 'baz')

    def test_parameterized(self):
        # FIXME Lint doesn't like that our decorator doesn't define __call__
        @FooDecorator(bar='qux')
        def foo():
            ...

        self.assertIsNotNone(foo.fn)
        self.assertEqual(foo.bar, 'qux')

    def test_name(self):
        self.assertEqual(FooDecorator.__name__, 'FooDecorator')

    def test_call(self):
        @FooDecorator
        def foo():
            ...

        for i in [1, 2]:
            foo()
            self.assertEqual(foo.call_count, i)


if __name__ == '__main__':
    unittest.main()
