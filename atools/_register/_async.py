import typing

from . import _base as Base  # noqa


type Decoratee[** Params, Return] = typing.Callable[Params, typing.Awaitable[Return]]


class Decorated[_Decorated, ** Params, Return](Base.Decorated[_Decorated]):
    __call__: typing.Callable[Params, typing.Awaitable[Return]]


type Decoration[Params, Return] = Base.Decoration[Decoratee[Params, Return]]
