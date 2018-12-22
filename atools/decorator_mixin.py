from typing import Awaitable, Callable, Dict, Optional, Union

Fn = Union[Awaitable, Callable]


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
