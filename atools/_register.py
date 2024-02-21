from __future__ import annotations

import dataclasses
import typing

from ._key import Key


type _Registry[T] = dict[Key.Key, T | set[str]]


class _Decoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, Return]


@dataclasses.dataclass(frozen=True, kw_only=True)
class _Decoration[** Params, Return]:
    registry: _Registry[_Decoratee]


class _Decorated[** Params, Return](_Decoratee[Params, Return], Key.Decorated):
    register: _Decoration[Params, Return]


@dataclasses.dataclass(frozen=True, init=False)
class _Decorator:
    _name: Key.Name = ...

    registry: _Registry = ...

    _default_registry: typing.ClassVar[type[_Registry]] = {}
    Decorated: typing.ClassVar[type[_Decorated]] = _Decorated
    Decoration: typing.ClassVar[type[_Decoration]] = _Decoration

    def __init__(self, _name: Key.Name = ..., /, registry: _Registry = ...) -> None:
        object.__setattr__(self, '_name', _name)
        object.__setattr__(self, 'registry', self._default_registry if registry is ... else registry)

    def __call__[** Params, Return](self, decoratee: _Decoratee[Params, Return], /) -> _Decorated[Params, Return]:
        decoratee = Key(self._name)(decoratee)

        # Create all the registry links that lead up to the entrypoint decoration.
        for i in range(1, len(decoratee.key)):
            self.registry.setdefault(decoratee.key[:i], set()).add(decoratee.key[i])

        # Add the entrypoint decoration to the registry.
        self.registry[decoratee.key] = decoratee

        decoratee.register = _Decoration[Params, Return](registry=self.registry)
        decoratee: _Decorated[Params, Return]

        return decoratee


Register = _Decorator
