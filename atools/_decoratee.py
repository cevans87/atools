import abc
import typing


@typing.final
class Decorated(abc.ABC):

    type Async[** Params, Return] = typing.Callable[Params, typing.Awaitable[Return]]
    type Multi[** Params, Return] = typing.Callable[Params, Return]
    type Top[** Params, Return] = Decorated.Async[Params, Return] | Decorated.Multi[Params, Return]
    ...
