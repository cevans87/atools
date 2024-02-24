import typing

from . import _base as Base  # noqa

type Decoratee[** Params, Return] = typing.Callable[Params, Return]
type Decoration = Base.Decoration


class Decorated[** Params, Return](Base.Decorated, typing.Protocol):
    __call__: typing.Callable[Params, Return]
