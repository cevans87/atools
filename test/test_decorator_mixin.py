from atools import DecoratorMixin
import inspect
from typing import Any
import unittest
from unittest.mock import MagicMock


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

        self.assertIsNotNone(foo.foo_decorator.fn)
        self.assertEqual(foo.foo_decorator.bar, 'baz')

    def test_signature_is_same_as_decorator(self):
        self.assertEqual(inspect.signature(foo_decorator), inspect.signature(_FooDecorator))

    def test_parameterized(self):
        @foo_decorator(bar='qux')
        def foo():
            ...

        self.assertIsNotNone(foo.foo_decorator.fn)
        self.assertEqual(foo.foo_decorator.bar, 'qux')

    def test_name(self):
        self.assertEqual(foo_decorator.__name__, 'foo_decorator')

    def test_call(self):
        @foo_decorator
        def foo():
            ...

        for i in [1, 2]:
            foo()
            self.assertEqual(foo.foo_decorator.call_count, i)

    def test_doc(self) -> None:
        self.assertEqual(foo_decorator.__doc__, _FooDecorator.__doc__)

    def test_class(self) -> None:
        @foo_decorator
        class Foo:
            pass

        self.assertTrue(isinstance(Foo(), Foo))

    def test_class_method(self) -> None:
        outer_self = self
        body = MagicMock()

        class Foo:
            @foo_decorator
            def foo(self) -> None:
                body()
                outer_self.assertTrue(isinstance(self, Foo))

        Foo().foo()
        body.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
