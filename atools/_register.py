from __future__ import annotations

import dataclasses
import typing

from . import _key


class Decoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, Return]


class Decorated[** Params, Return](Decoratee[Params, Return], _key.Decorated):
    register: Decoration


@dataclasses.dataclass(frozen=True, kw_only=True)
class Register:
    decorateds: dict[_key.Key, Decorated] = dataclasses.field(default_factory=dict)
    links: dict[_key.Key, set[_key.Name]] = dataclasses.field(default_factory=dict)


Decoration = Register


@dataclasses.dataclass(frozen=True)
class Decorator:
    _prefix: _key.Name = ...
    _suffix: _key.Name = ...
    _: dataclasses.KW_ONLY = ...
    register: Register = ...

    _default_register: typing.ClassVar[dict[_key.Key, Register]] = Decoration()

    Decorated: typing.ClassVar[type[Decorated]] = Decorated
    Decoration: typing.ClassVar[type[Decoration]] = Decoration

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
        decoration.decorateds[decoratee.key] = decoratee

        return decoratee

    def get_register(self) -> Register:
        return self.register if self.register is not ... else self._default_register
