from atools import DecoratorMixin
from typing import Any
import unittest


class _FooDecorator:
    """FooDoc"""
    def __init__(self, fn, *, bar='baz') -> None:
        self.fn = fn
        self.bar = bar
        self.call_count = 0

    def __call__(self, *args, **kwargs) -> Any:
        self.call_count += 1
        return self.fn(*args, **kwargs)


foo_decorator = type('foo_decorator', (DecoratorMixin, _FooDecorator), {})


class TestDecoratorMeta(unittest.TestCase):
    def test_un_parameterized(self):
        @foo_decorator
        def foo():
            ...

        self.assertIsNotNone(foo.fn)
        self.assertEqual(foo.bar, 'baz')

    def test_parameterized(self):
        @foo_decorator(bar='qux')
        def foo():
            ...

        self.assertIsNotNone(foo.fn)
        self.assertEqual(foo.bar, 'qux')

    def test_name(self):
        self.assertEqual(foo_decorator.__name__, 'foo_decorator')

    def test_call(self):
        @foo_decorator
        def foo():
            ...

        for i in [1, 2]:
            foo()
            self.assertEqual(foo.call_count, i)

    def test_doc(self) -> None:
        self.assertEqual(foo_decorator.__doc__, _FooDecorator.__doc__)


if __name__ == '__main__':
    unittest.main(verbosity=2)
