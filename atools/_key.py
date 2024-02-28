from __future__ import annotations
import abc
import annotated_types
import dataclasses
import re
import typing

from . import _base

type Name = typing.Annotated[str, annotated_types.Predicate(str.isidentifier)]  # noqa

Decoratee = _base.Decorated
Decorated = _base.Decorated


@typing.final
class Decoration(_base.Decoration):

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class Base[** Params, Return](_base.Decoration.Base):
        key: tuple[str, ...] = dataclasses.field(init=False)

    class Async[** Params, Return](Base[Params, Return]):
        ...

    class Multi[** Params, Return](Base[Params, Return]):
        ...


@dataclasses.dataclass(frozen=True)
class Decorator[** Params, Return]:
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
    def decoration(self) -> Decoration.Base[Params, Return]:
        return Decoration([
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
