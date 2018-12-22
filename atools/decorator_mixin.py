from typing import Awaitable, Callable, Dict, Optional, Union

Fn = Union[Awaitable, Callable]


class DecoratorMeta(type):
    """DecoratorMeta allows a decorator class to always receive its function in __init__."""

    def __call__(cls, _fn: Optional[Fn] = None, **kwargs) -> Callable:

        if _fn is not None:
            return super().__call__(_fn, **kwargs)
        else:
            return lambda _fn: DecoratorMeta.__call__(cls, _fn, **kwargs)


class DecoratorMixin:

    __fn: Optional[Callable] = None
    __kwargs: Optional[Dict] = None

    def __init__(self, _fn: Optional[Fn] = None, **kwargs):
        if _fn is None:
            self.__kwargs = kwargs
        else:
            self.__fn = _fn
            super().__init__(_fn, **kwargs)

    def __call__(self, *args, **kwargs):
        if self.__fn is None:
            self.__init__(args[0], **self.__kwargs)
            return self
        else:
            # noinspection PyUnresolvedReferences
            return super().__call__(*args, **kwargs)
