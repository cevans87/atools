import typing

from . import _base as Base  # noqa


type Decoratee[** Params, Return] = typing.Callable[Params, Return]


class Decorated[_Decorated, ** Params, Return](Base.Decorated[_Decorated]):
    __call__: typing.Callable[Params, Return]


type Decoration[Params, Return] = Base.Decoration[Decoratee[Params, Return]]
