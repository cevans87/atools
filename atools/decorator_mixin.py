from functools import wraps
import inspect
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple, Type, Union

Fn = Union[Awaitable, Callable]
Cls = Type
Decoratee = Union[Cls, Fn]
Decorated = Union[Cls, Decoratee]
Decorator = Union[Cls, Decoratee]


class _DecoratorMeta(type):
    def __new__(
            mcs, name: str, bases: Tuple[Type, ...], namespace: Dict[str, Any]
    ) -> '_DecoratorMeta':
        # DecoratorMixin has a __doc__, but we want the __doc__ from the actual decorator class.
        if len(bases) > 1 and bases[0] is DecoratorMixin and '__doc__' not in namespace:
            namespace['__doc__'] = bases[1].__doc__
            namespace['__wrapped__'] = bases[1]

        return super().__new__(mcs, name, bases, namespace)

    def __call__(cls, _decoratee: Optional[Decoratee] = None, **kwargs) -> Decorated:
        if _decoratee is None:
            return lambda decoratee: cls(decoratee, **kwargs)

        decorator = super().__call__(_decoratee, **kwargs)

        if inspect.isclass(decorator):
            decorated = decorator
        elif inspect.isclass(_decoratee):
            # _decoratee is a class. Our decorator should have already done its work.
            decorated = _decoratee
        else:
            # _decoratee is a function. The returned type needs to also be a function.
            @wraps(_decoratee)
            def decorated(*inner_args, **inner_kwargs):
                return decorator(*inner_args, **inner_kwargs)

            setattr(decorated, type(decorator).__name__, decorator)

        return decorated


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
    pass
