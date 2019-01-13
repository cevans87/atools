from __future__ import annotations
from asyncio import get_event_loop
from atools.decorator_mixin import DecoratorMixin, Fn, Decoratee, Decorator
import inspect
from typing import Any


class _AsyncTestCase:
    """Decorates a test function or test class to enable running async test functions.

    Examples:
        - After decorating a test function, simply calling it will run it.
            async def test_foo(): -> None: ...

            test_foo()  # Returns a coroutine, but it wasn't awaited, so the test didn't run.

            @async_test_case
            async def test_foo(): -> None: ...

            test_foo()  # The decorator awaits the decorated function.

        - Test class may be decorated. All async functions with names starting with 'test' are
          decorated.
            @async_test_case
            Class TestFoo(unittest.TestCase):
                # All of these functions are decorated. Nothing else is needed for them to run.
                async def test_foo(self) -> None: ...
                async def test_bar(self) -> None: ...
                async def test_baz(self) -> None: ...
    """

    def __new__(cls, decoratee: Decoratee) -> Decorator:
        if inspect.isclass(decoratee):
            for k, v in decoratee.__dict__.items():
                if k.startswith('test') and inspect.iscoroutinefunction(v):
                    setattr(decoratee, k, async_test_case(v))

        return super().__new__(cls)

    def __init__(self, fn: Fn) -> None:
        self.fn = fn

    def __call__(self, *args, **kwargs) -> Any:
        return get_event_loop().run_until_complete(self.fn(*args, **kwargs))


async_test_case = type('async_test_case', (DecoratorMixin, _AsyncTestCase), {})