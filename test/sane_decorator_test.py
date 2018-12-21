import unittest

import sane_decorator


class FooDecorator:
    def __init__(self, fn, *, bar='baz') -> None:
        self.fn = fn
        self.bar = bar


foo_decorator = sane_decorator.SaneDecorator(FooDecorator)


class TestSaneDecoratorMixin(unittest.TestCase):
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
        self.assertEqual(type(foo_decorator).__name__, 'FooDecorator')


if __name__ == '__main__':
    unittest.main()
