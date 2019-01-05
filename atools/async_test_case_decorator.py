from __future__ import annotations
from asyncio import get_event_loop
from atools.decorator_mixin import DecoratorMixin, Fn, Decoratee, Decorator
import inspect
from typing import Any


class _AsyncTestCase:

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
