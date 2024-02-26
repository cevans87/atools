from __future__ import annotations
import abc
import dataclasses
import typing

from . import _decoratee, _key


@typing.final
class Register(abc.ABC):

    # The lack of type parameters for the following classes is intentional. Base.decoratees may hold decoratees with any
    #  kind of params and return, and allowing type narrowing with parameterization here would lead to incorrect
    #  annotations.
    @dataclasses.dataclass(frozen=True, kw_only=True)
    class Base:
        decoratees: dict[_key.Key, Decoratee.Top] = dataclasses.field(default_factory=dict)
        links: dict[_key.Key, set[_key.Name]] = dataclasses.field(default_factory=dict)

    class Async(Base):
        ...

    class Multi(Base):
        ...

    class Top(Async, Multi):
        ...


Decoratee = _decoratee.Decorated


@typing.final
class Decorated(abc.ABC):

    @typing.runtime_checkable
    class Base[** Params, Return](typing.Protocol):
        registry: Register.Base

    @typing.runtime_checkable
    class Async[** Params, Return](Base[Params, Return], typing.Protocol):
        ...

    @typing.runtime_checkable
    class Multi[** Params, Return](Base[Params, Return], typing.Protocol):
        ...

    @typing.runtime_checkable
    class Top[** Params, Return](Async[Params, Return], Multi[Params, Return], typing.Protocol):
        ...


type Decoration = Register


@typing.final
class Decorator(abc.ABC):

    @dataclasses.dataclass(frozen=True)
    class Base[** Params, Return](_key.Decorator.Base[Params, Return], abc.ABC):
        register: Register.Top = Register.Base()

        @typing.overload
        def __call__(self, decoratee: Decoratee.Async[Params, Return], /) -> Decorated.Async[Params, Return]: ...

        @typing.overload
        def __call__(self, decoratee: Decoratee.Multi[Params, Return], /) -> Decorated.Multi[Params, Return]: ...

        def __call__(self, decoratee: Decoratee.Top[Params, Return], /) -> Decorated.Top[Params, Return]:
            if not isinstance(decoratee, Decorated.Base):
                decoratee = _key.Decorator.Top[Params, Return](self._prefix, self._suffix)(decoratee)

                # Create all the register links that lead up to the entrypoint decoration.
                for i in range(len(decoratee.key)):
                    self.register.links.setdefault(decoratee.key[:i], set()).add(decoratee.key[i])
                self.register.links.setdefault(decoratee.key, set())

                decoratee.register = self.register

            decorated: Decorated.Top[Params, Return].Top = decoratee

            self.register.decoratees[decorated.key] = decoratee

            return decorated

    class Async[** Params, Return](Base[Params, Return]):
        __call__: typing.Callable[[Decoratee.Async[Params, Return]], Decorated.Async[Params, Return]]

    class Multi[** Params, Return](Base[Params, Return]):
        __call__: typing.Callable[[Decoratee.Multi[Params, Return]], Decorated.Multi[Params, Return]]

    class Top[** Params, Return](Async[Params, Return], Multi[Params, Return]):

        @typing.overload
        def __call__(self, decoratee: Decoratee.Async[Params, Return], /) -> Decorated.Async[Params, Return]: ...

        @typing.overload
        def __call__(self, decoratee: Decoratee.Multi[Params, Return], /) -> Decorated.Multi[Params, Return]: ...

        def __call__(self, decoratee: Decoratee.Top[Params, Return], /) -> Decorated.Top[Params, Return]:
            return super().__call__(decoratee)
