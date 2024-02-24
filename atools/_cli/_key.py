from __future__ import annotations
import annotated_types
import dataclasses
import re
import typing

Name = typing.Annotated[str, annotated_types.Predicate(lambda name: re.match(r'^[.a-z]*$', name) is not None)]


class Key(
    tuple[typing.Annotated[
        str, annotated_types.Predicate(lambda value: re.search(r'^[a-z]*$', value) is not None)
    ], ...]
): ...


Decoration = Key

type AsyncDecoratee[** Params, Return] = typing.Callable[Params, typing.Awaitable[Return]]
type SyncDecoratee[** Params, Return] = typing.Callable[Params, Return]
type Decoratee[** Params, Return] = AsyncDecoratee[Params, Return] | SyncDecoratee[Params, Return]


class DecoratedBase:
    key: Key


class AsyncDecorated[** Params, Return](DecoratedBase):
    __call__: typing.Callable[Params, typing.Awaitable[Return]]


class SyncDecorated[** Params, Return](DecoratedBase):
    __call__: typing.Callable[Params, Return]


type Decorated[** Params, Return] = AsyncDecorated[Params, Return] | SyncDecorated[Params, Return]


@dataclasses.dataclass(frozen=True)
class Decorator:
    _prefix: Name = ...
    _suffix: Name = ...
    _: dataclasses.KW_ONLY = ...

    Decorated: typing.ClassVar[type[Decorated]] = Decorated
    Decoration: typing.ClassVar[type[Decoration]] = Decoration

    Key: typing.ClassVar[type[Key]] = Key
    Name: typing.ClassVar[type[Name]] = Name

    @typing.overload
    def __call__[** Params, Return](
        self, decoratee: AsyncDecoratee[Params, Return], /
    ) -> AsyncDecorated[Params, Return]: ...

    @typing.overload
    def __call__[** Params, Return](
        self, decoratee: SyncDecoratee[Params, Return], /
    ) -> SyncDecorated[Params, Return]: ...

    def __call__[** Params, Return](self, decoratee: Decoratee[Params, Return], /) -> Decorated[Params, Return]:
        if isinstance(getattr(decoratee, 'key', None), Decoration):
            decoratee: Decorated[Params, Return]
        else:
            prefix = self._prefix if self._prefix is not ... else decoratee.__module__
            suffix = self._suffix if self._prefix is not ... or self._suffix is not ... else re.sub(
                r'.<.*>', '', decoratee.__qualname__
            )

            decoratee.key = Decorator(prefix, suffix).key
            decoratee: Decorated[Params, Return]

        decorated: Decorated[Params, Return] = decoratee

        return decorated

    @property
    def key(self) -> Key:
        return Key(tuple([
            *([] if self._prefix is ... else re.sub(r'.<.*>', '', self._prefix).split('.')),
            *([] if self._suffix is ... else re.sub(r'.<.*>', '', self._suffix).split('.')),
        ]))

