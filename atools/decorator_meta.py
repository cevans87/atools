from typing import Awaitable, Callable, Optional, Union

Fn = Union[Awaitable, Callable]


class DecoratorMeta(type):
    """DecoratorMeta allows a decorator class to always receive its function in __init__."""

    def __call__(cls, _fn: Optional[Fn] = None, **kwargs) -> Callable:

        if _fn is not None:
            return super().__call__(_fn, **kwargs)
        else:
            return lambda _fn: DecoratorMeta.__call__(cls, _fn, **kwargs)
