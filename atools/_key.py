from __future__ import annotations
import abc
import annotated_types
import dataclasses
import re
import typing


@typing.final
class Name(abc.ABC):
    type Base = typing.Annotated[str, annotated_types.Predicate(str.isidentifier)]  # noqa
    type Async = Name.Base
    type Multi = Name.Base
    type Top = Name.Async | Name.Multi
    ...


@typing.final
class Key(abc.ABC):
    type Base = tuple[typing.Annotated[str, annotated_types.Predicate(str.isidentifier)], ...]  # noqa
    type Async = Key.Base
    type Multi = Key.Base
    type Top = Key.Async | Key.Multi
    ...


@typing.final
class Decoratee[** Params, Return](abc.ABC):
    type Async = typing.Callable[Params, typing.Awaitable[Return]]
    type Multi = typing.Callable[Params, Return]
    type Top = Decoratee[Params, Return].Async | Decoratee[Params, Return].Multi
    ...


@typing.final
class Decorated[** Params, Return](abc.ABC):
    @typing.runtime_checkable
    class Base(typing.Protocol):
        key: Key.Top
    type Async = Decorated[Params, Return].Base
    type Multi = Decorated[Params, Return].Base
    type Top = Decorated[Params, Return].Async | Decorated[Params, Return].Multi
    ...


type Decoration = Key


@typing.final
class Decorator[** Params, Return](abc.ABC):

    @dataclasses.dataclass(frozen=True)
    class Base:
        _prefix: Name = ...
        _suffix: Name = ...

        def __call__(self, decoratee: Decoratee[Params, Return].Base, /) -> Decorated[Params, Return].Base:
            if not isinstance(decoratee, Decorated[Params, Return].Base):
                prefix = self._prefix if self._prefix is not ... else decoratee.__module__
                suffix = self._suffix if self._prefix is not ... or self._suffix is not ... else re.sub(
                    r'.<.*>', '', decoratee.__qualname__
                )

                decoratee.key = tuple([
                    *([] if prefix is ... else re.sub(r'.<.*>', '', prefix).split('.')),
                    *([] if suffix is ... else re.sub(r'.<.*>', '', suffix).split('.')),
                ])
                decoratee: Decorated[Params, Return].Top

            decorated: Decorated[Params, Return].Top = decoratee

            return decorated

    class Async(Base):
        __call__: typing.Callable[[Decoratee[Params, Return].Async], Decorated[Params, Return].Async]

    class Multi(Base):
        __call__: typing.Callable[[Decoratee[Params, Return].Multi], Decorated[Params, Return].Multi]

    @dataclasses.dataclass(frozen=True)
    class Top(Async, Multi):

        @typing.overload
        def __call__(self, decoratee: Decoratee[Params, Return].Async, /) -> Decorated[Params, Return].Async: ...

        @typing.overload
        def __call__(self, decoratee: Decoratee[Params, Return].Multi, /) -> Decorated[Params, Return].Multi: ...

        def __call__(self, decoratee: Decoratee[Params, Return].Top, /) -> Decorated[Params, Return].Top:
            return super().__call__(decoratee)
