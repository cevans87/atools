from __future__ import annotations
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple, Type, Union

Fn = Union[Awaitable, Callable]


class _DecoratorMeta(type):
    def __new__(
            mcs, name: str, bases: Tuple[Type, ...], namespace: Dict[str, Any]
    ) -> _DecoratorMeta:

        # DecoratorMixin has a __doc__, but we want the __doc__ from the actual decorator class.
        if len(bases) > 1 and bases[0] is DecoratorMixin and '__doc__' not in namespace:
            namespace['__doc__'] = bases[1].__doc__

        return super().__new__(mcs, name, bases, namespace)


class DecoratorMixin(metaclass=_DecoratorMeta):
    """Mixin that makes it easier to write a class-based decorator with optional kwargs.

    Decorators that use this mixin only need to define an __init__ function and a __call__ function.

    For classes that will use this mixin:

        __init__ will always receive the the function that is being decorated followed by any
        keyword arguments given to the decorator.

        __call__ will always receive the call arguments given directly to the decorated function.

    Decorators may be defined as follows:

        class _FooDecorator:
            def __init__(fn, bar=None):
                self._fn = fn

            def __call__(*args,  **kwargs):
                self._fn(*args, **kwargs


        foo_decorator = type('foo_decorator', (DecoratorMixin, _FooDecorator), {})

    and then may be used in any of the following manners:

        @foo_decorator
        def foo():
            ...

        @foo_decorator()
        def foo():
            ...

        @foo_decorator(bar='bar')
        def foo():
            ...
    """

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
