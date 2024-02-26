from __future__ import annotations
import abc
import annotated_types
import dataclasses
import re
import typing

from . import _decoratee

type Key = tuple[typing.Annotated[str, annotated_types.Predicate(str.isidentifier)], ...]  # noqa
type Name = typing.Annotated[str, annotated_types.Predicate(str.isidentifier)]  # noqa


Decoratee = _decoratee.Decorated


@typing.final
class Decorated(abc.ABC):

    @typing.runtime_checkable
    class Base[** Params, Return](typing.Protocol):
        key: Key

    @typing.runtime_checkable
    class Async[** Params, Return](Base[Params, Return], typing.Protocol):
        __call__: typing.Callable[Params, typing.Awaitable[Return]]

    @typing.runtime_checkable
    class Multi[** Params, Return](Base[Params, Return], typing.Protocol):
        __call__: typing.Callable[Params, Return]

    @typing.runtime_checkable
    class Top[** Params, Return](Async[Params, Return], Multi[Params, Return], typing.Protocol):
        __call__: typing.Callable[Params, typing.Awaitable[Return] | Return]


type Decoration = Key


@typing.final
class Decorator(abc.ABC):

    @dataclasses.dataclass(frozen=True)
    class Base[** Params, Return]:
        _prefix: Name = ...
        _suffix: Name = ...

        def __call__(self, decoratee: Decoratee.Base[Params, Return], /) -> Decorated.Base[Params, Return]:
            if not isinstance(decoratee, Decorated.Base):
                prefix = self._prefix if self._prefix is not ... else decoratee.__module__
                suffix = self._suffix if self._prefix is not ... or self._suffix is not ... else re.sub(
                    r'.<.*>', '', decoratee.__qualname__
                )

                decoratee.key = tuple([
                    *([] if prefix is ... else re.sub(r'.<.*>', '', prefix).split('.')),
                    *([] if suffix is ... else re.sub(r'.<.*>', '', suffix).split('.')),
                ])
                decoratee: Decorated.Top[Params, Return]

            decorated: Decorated.Top[Params, Return] = decoratee

            return decorated

        @property
        def key(self) -> Key:
            return tuple([
                *([] if self._prefix is ... else re.sub(r'.<.*>', '', self._prefix).split('.')),
                *([] if self._suffix is ... else re.sub(r'.<.*>', '', self._suffix).split('.')),
            ])

    class Async[** Params, Return](Base[Params, Return]):
        __call__: typing.Callable[[Decoratee.Async[Params, Return]], Decorated.Async[Params, Return]]

    class Multi[** Params, Return](Base[Params, Return]):
        __call__: typing.Callable[[Decoratee.Multi[Params, Return]], Decorated.Multi[Params, Return]]

    @dataclasses.dataclass(frozen=True)
    class Top[** Params, Return](Async[Params, Return], Multi[Params, Return]):

        @typing.overload
        def __call__(self, decoratee: Decoratee.Async[Params, Return], /) -> Decorated.Async[Params, Return]: ...

        @typing.overload
        def __call__(self, decoratee: Decoratee.Multi[Params, Return], /) -> Decorated.Multi[Params, Return]: ...

        def __call__(self, decoratee: Decoratee.Top[Params, Return], /) -> Decorated.Top[Params, Return]:
            return super().__call__(decoratee)
