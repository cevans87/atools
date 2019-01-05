import unittest
from atools import async_test_case
from unittest.mock import MagicMock


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


if __name__ == '__main__':
    unittest.main(verbosity=2)
