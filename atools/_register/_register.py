from __future__ import annotations

import dataclasses
import typing

from . import _key


type AsyncDecoratee[** Params, Return] = typing.Callable[Params, typing.Awaitable[Return]]
type SyncDecoratee[** Params, Return] = typing.Callable[Params, Return]
type Decoratee[** Params, Return] = AsyncDecoratee[Params, Return] | SyncDecoratee[Params, Return]


class DecoratedBase(_key.Base.DecoratedBase):
    register: Decoration


class AsyncDecorated[** Params, Return](DecoratedBase):
    __call__: typing.Callable[Params, typing.Awaitable[Return]]


class SyncDecorated[** Params, Return](DecoratedBase):
    __call__: typing.Callable[Params, Return]


type Decorated[** Params, Return] = AsyncDecorated[Params, Return] | SyncDecorated[Params, Return]


@dataclasses.dataclass(frozen=True, kw_only=True)
class Register:
    decoratees: dict[_key.Key, Decoratee] = dataclasses.field(default_factory=dict)
    links: dict[_key.Key, set[_key.Name]] = dataclasses.field(default_factory=dict)


Decoration = Register


class DecoratedBase:
    register: Decoration


@dataclasses.dataclass(frozen=True)
class Decorator:
    _prefix: _key.Name = ...
    _suffix: _key.Name = ...
    _: dataclasses.KW_ONLY = ...
    register: Register = ...

    _default_register: typing.ClassVar[dict[_key.Key, Register]] = Decoration()

    @typing.overload
    def __call__[** Params, Return](
        self, decoratee: AsyncDecoratee[Params, Return], /
    ) -> AsyncDecorated[Params, Return]: ...

    @typing.overload
    def __call__[** Params, Return](
        self, decoratee: SyncDecoratee[Params, Return], /
    ) -> SyncDecorated[Params, Return]: ...

    def __call__[** Params, Return](self, decoratee: Decoratee[Params, Return], /) -> Decorated[Params, Return]:
        if isinstance(getattr(decoratee, 'register', None), Decoration):
            decoratee: Decorated[Params, Return]
            return decoratee

        decoratee = _key.Decorator(self._prefix, self._suffix)(decoratee)
        decoration = self.register if self.register is not ... else self._default_register

        # Create all the register links that lead up to the entrypoint decoration.
        for i in range(len(decoratee.key)):
            decoration.links.setdefault(decoratee.key[:i], set()).add(decoratee.key[i])
        decoration.links.setdefault(decoratee.key, set())

        decoratee.register = decoration
        decoratee: Decorated[Params, Return]

        # Add the entrypoint decoration to the register.
        decoration.decoratees[decoratee.key] = decoratee

        return decoratee

    def get_register(self) -> Register:
        return self.register if self.register is not ... else self._default_register
