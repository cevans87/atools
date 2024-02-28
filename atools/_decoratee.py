import abc
import typing


@typing.final
class Decorated(abc.ABC):

    @typing.runtime_checkable
    class Base[** Params, Return](typing.Protocol):
        decoratee: typing.Callable[[...], ...]

    @typing.runtime_checkable
    class Async[** Params, Return](Base[Params, Return], typing.Protocol):
        decoratee: typing.Callable[Params, typing.Awaitable[Return]]

    @typing.runtime_checkable
    class Multi[** Params, Return](Base[Params, Return], typing.Protocol):
        decoratee: typing.Callable[Params, Return]

    @typing.runtime_checkable
    class Top[** Params, Return](Async[Params, Return], Multi[Params, Return], typing.Protocol):
        decoratee: typing.Callable[Params, typing.Awaitable[Return] | Return]
