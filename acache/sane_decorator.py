from __future__ import annotations
from typing import Any, Awaitable, Callable, Optional, Union

Fn = Union[Awaitable, Callable]
Decorator = Callable[[Fn, Any], Any]


class SaneDecorator:
    """SaneDecorator allows a decorator to be parameterized or un-parameterized."""

    def __new__(cls, decorator: Decorator, **kwargs):
        cls.__name__ = decorator.__name__
        return super().__new__(cls)

    def __init__(self, decorator: Decorator, **kwargs) -> None:
        self._decorator = decorator
        self._kwargs = kwargs

    def __call__(self, _fn: Optional[Fn] = None, **kwargs) -> Union[Decorator, SaneDecorator]:
        if _fn is not None:
            return self._decorator(_fn, **self._kwargs)
        else:
            return SaneDecorator(self._decorator, **kwargs)
