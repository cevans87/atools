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


class Decoratee[** Params, Return](typing.Callable[Params, Return]):
    __call__: typing.Callable[Params, Return]


class Decorated[** Params, Return](Decoratee[Params, Return]):
    key: Key


@dataclasses.dataclass(frozen=True)
class Decorator:
    _prefix: Name = ...
    _suffix: Name = ...
    _: dataclasses.KW_ONLY = ...

    Decorated: typing.ClassVar[type[Decorated]] = Decorated
    Decoration: typing.ClassVar[type[Decoration]] = Decoration

    Key: typing.ClassVar[type[Key]] = Key
    Name: typing.ClassVar[type[Name]] = Name

    def __call__[** Params, Return](self, decoratee: Decoratee[Params, Return], /) -> Decorated[Params, Return]:
        if isinstance(getattr(decoratee, 'key', None), Key):
            decoratee: Decorated[Params, Return]
            return decoratee

        prefix = self._prefix if self._prefix is not ... else decoratee.__module__
        suffix = self._suffix if self._prefix is not ... or self._suffix is not ... else re.sub(
            r'.<.*>', '', decoratee.__qualname__
        )

        decoratee.key = Decorator(prefix, suffix).key

        decoratee: Decorated[Params, Return]

        return decoratee

    @property
    def key(self) -> Key:
        return Key(tuple([
            *([] if self._prefix is ... else re.sub(r'.<.*>', '', self._prefix).split('.')),
            *([] if self._suffix is ... else re.sub(r'.<.*>', '', self._suffix).split('.')),
        ]))

