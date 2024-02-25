import typing

from . import _base as Base  # noqa


type Call[** Params, Return] = typing.Callable[Params, Return]
type Register[** Params, Return] = Base.Register[Decorated[Params, Return]]
type Decoratee[** Params, Return] = Base.Decoratee[Call[Params, Return]]
type Decorated[** Params, Return] = Register[Params, Return]
type Decorator[** Params, Return] = Base.Decorator[Decorated[Params, Return]]