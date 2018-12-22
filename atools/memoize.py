from decorator_mixin import DecoratorMeta, Fn
from typing import Any


class Memoize(metaclass=DecoratorMeta):

    def __init__(self, fn: Fn) -> None:
        self._fn = fn

    def __call__(self, *args, **kwargs) -> Any:
        return self._fn(*args, **kwargs)
