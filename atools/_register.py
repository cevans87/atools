from __future__ import annotations
import abc
import dataclasses
import typing

from . import _key


@typing.final
class Register(abc.ABC):
    @dataclasses.dataclass(frozen=True, kw_only=True)
    class Base:
        decorateds: dict[_key.Key, Decorated.Top] = dataclasses.field(default_factory=dict)
        links: dict[_key.Key, set[_key.Name]] = dataclasses.field(default_factory=dict)

    class Async(Base):
        ...

    class Multi(Base):
        ...

    class Top(Async, Multi):
        ...


@typing.final
class Decoratee[** Params, Return](abc.ABC):

    @typing.runtime_checkable
    class Async(typing.Protocol):
        async def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return: ...

    @typing.runtime_checkable
    class Multi(typing.Protocol):
        def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return: ...

    @typing.runtime_checkable
    class Top(Async, Multi):

        @typing.overload
        async def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return: ...

        @typing.overload
        def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return: ...

        def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return | typing.Awaitable[Return]: ...


@typing.final
class Decorated[** Params, Return](abc.ABC):

    @typing.runtime_checkable
    class Base(typing.Protocol):
        registry: Register.Base

    class Async(Base):
        ...

    class Multi(Base):
        ...

    class Top(Async, Multi):
        ...


type Decoration = Register


@typing.final
class Decorator[** Params, Return](abc.ABC):

    @dataclasses.dataclass(frozen=True)
    class Base(_key.Decorator[Params, Return].Base):
        register: Register.Top = Register.Base()

        def __call__(self, decoratee: Decoratee[Params, Return].Base, /) -> Decorated[Params, Return].Base:
            if not isinstance(decoratee, Decorated[Params, Return].Base):
                decoratee = _key.Decorator[Params, Return].Base(self._prefix, self._suffix)(decoratee)

                # Create all the register links that lead up to the entrypoint decoration.
                for i in range(len(decoratee.key)):
                    self.register.links.setdefault(decoratee.key[:i], set()).add(decoratee.key[i])
                self.register.links.setdefault(decoratee.key, set())

                decoratee.register = self.register
                decoratee: Decorated[Params, Return]

                # Add the entrypoint decoration to the register.

            decorated: Decorated[Params, Return].Top = decoratee

            self.register.decorateds[decorated.key] = decoratee

            return decorated

    class Async(Base):
        __call__: typing.Callable[[Decoratee[Params, Return].Async], Decorated[Params, Return].Async]

    class Multi(Base):
        __call__: typing.Callable[[Decoratee[Params, Return].Multi], Decorated[Params, Return].Multi]

    class Top(Async, Multi):

        @typing.overload
        def __call__(self, decoratee: Decoratee[Params, Return].Async, /) -> Decorated[Params, Return].Async: ...

        @typing.overload
        def __call__(self, decoratee: Decoratee[Params, Return].Multi, /) -> Decorated[Params, Return].Multi: ...

        def __call__(self, decoratee: Decoratee[Params, Return].Top, /) -> Decorated[Params, Return].Top:
            return super().__call__(decoratee)
