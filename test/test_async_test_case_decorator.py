import unittest
from atools import async_test_case
from atools.decorator_mixin import Fn
from unittest.mock import MagicMock, patch
from typing import Any


class TestAsyncTestCase(unittest.TestCase):

    def test_fn_decorator_works(self) -> None:
        body = MagicMock()

        @async_test_case
        async def foo() -> None:
            body()

        foo()
        body.assert_called_once()

    def test_cls_decorator_decorates_test_fns(self) -> None:
        body = MagicMock()
        outer_self = self

        @async_test_case
        class Foo:
            async def test_foo(self) -> None:
                outer_self.assertTrue(isinstance(self, Foo))
                body()

        Foo().test_foo()
        body.assert_called_once()

    def test_cls_decorator_with_patch_blocking_it_raises(self) -> None:
        class Bar:
            bar = None

        @async_test_case
        class Foo:
            @patch.object(Bar, 'bar')
            async def test_foo(self, _m_bar: MagicMock) -> None:
                ...

        with self.assertRaises(RuntimeError):
            Foo().test_foo()


if __name__ == '__main__':
    unittest.main(verbosity=2)
