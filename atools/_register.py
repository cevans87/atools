from __future__ import annotations
import abc
import dataclasses
import typing

from . import _base, _key


@dataclasses.dataclass(frozen=True, kw_only=True)
class Register(abc.ABC):
    decoratees: dict[_key.Key, _base.Decoratee] = dataclasses.field(default_factory=dict)
    links: dict[_key.Key, set[_key.Name]] = dataclasses.field(default_factory=dict)


@typing.runtime_checkable
class Decorated[** Params, Return](_key.Decorated[Params, Return], typing.Protocol):
    register: Register


@typing.runtime_checkable
class AsyncDecorated[** Params, Return](
    Decorated[Params, Return], _key.AsyncDecorated[Params, Return], typing.Protocol
):
    ...


@typing.runtime_checkable
class MultiDecorated[** Params, Return](
    Decorated[Params, Return], _key.MultiDecorated[Params, Return], typing.Protocol
):
    ...


@dataclasses.dataclass(frozen=True)
class Decorator[**Params, Return](_key.Decorator[Params, Return]):
    register: Register = Register()

    @typing.overload
    def __call__(
        self, decoratee: _base.AsyncDecoratee[Params, Return], /
    ) -> AsyncDecorated[Params, Return]: ...

    @typing.overload
    def __call__(
        self, decoratee: _base.MultiDecoratee[Params, Return], /
    ) -> MultiDecorated[Params, Return]: ...

    def __call__(
        self, decoratee: _base.Decoratee[Params, Return], /
    ) -> Decorated[Params, Return]:
        assert not isinstance(decoratee, Decorated)
        if not isinstance(decoratee, _key.Decorated):
            decoratee = _key.Decorator()(decoratee)

        # Create all the register links that lead up to the entrypoint decoration.
        for i in range(len(decoratee.key)):
            self.register.links.setdefault(decoratee.key[:i], set()).add(decoratee.key[i])
        self.register.links.setdefault(decoratee.key, set())

        decoratee.register = self.register
        assert isinstance(decoratee, Decorated)

        decorated = self.register.decoratees[decorated.key] = decoratee

        return decorated
