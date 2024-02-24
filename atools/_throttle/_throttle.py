from __future__ import annotations
import dataclasses
import inspect
import types
import typing

from . import _context
from . import _key


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContext[** Params, Return](_context.AsyncContext[Params, Return]):
    decoratee: AsyncDecoratee[Params, Return]

    async def __call__(self, return_: Return) -> None: ...
    async def __aenter__(self) -> typing.Self: ...
    async def __aexit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None: ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class SyncContext[** Params, Return](_context.SyncContext[Params, Return]):
    decoratee: SyncDecoratee[Params, Return]

    def __call__(self, return_: Return) -> None: ...
    def __enter__(self) -> typing.Self: ...
    def __exit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None: ...


type Context[** Params, Return] = AsyncContext[Params, Return] | SyncContext[Params, Return]

type AsyncDecoratee[** Params, Return] = typing.Callable[Params, typing.Awaitable[Return]]
type SyncDecoratee[** Params, Return] = typing.Callable[Params, Return]
type Decoratee[** Params, Return] = AsyncDecoratee[Params, Return] | SyncDecoratee[Params, Return]


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncDecoration[** Params, Return]:
    decoratee: Decoratee[Params, typing.Awaitable[Return]]
    contexts: list[AsyncContext] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True, kw_only=True)
class SyncDecoration[** Params, Return]:
    decoratee: Decoratee[Params, Return]
    contexts: list[SyncContext] = dataclasses.field(default_factory=list)


type Decoration[** Params, Return] = AsyncDecoration[Params, Return] | SyncDecoration[Params, Return]


@dataclasses.dataclass(kw_only=True)
class AsyncDecoratedData[** Params, Return](_key.DecoratedBase):
    context: AsyncDecoration[Params, Return]


@dataclasses.dataclass(kw_only=True)
class AsyncDecorated[** Params, Return](AsyncDecoratedData[Params, Return]):
    async def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return: ...


@dataclasses.dataclass(kw_only=True)
class SyncDecoratedData[** Params, Return](_key.DecoratedBase):
    context: SyncDecoration[Params, Return]


@dataclasses.dataclass(kw_only=True)
class SyncDecorated[** Params, Return](SyncDecoratedData[Params, Return]):
    def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return: ...


type Decorated[** Params, Return] = AsyncDecorated[Params, Return] | SyncDecorated[Params, Return]


@dataclasses.dataclass(frozen=True)
class DecoratorData:
    _prefix: _key.Name
    _suffix: _key.Name


@dataclasses.dataclass(frozen=True)
class AsyncDecorator(DecoratorData):

    def __call__[** Params, Return](
        self, decoratee: AsyncDecoratee[Params, Return], /
    ) -> AsyncDecorated[Params, Return]:
        decoratee = _context.AsyncDecorator(self._prefix, self._suffix)(decoratee)
        decoratee.context.contexts.append(AsyncContext(decoratee=decoratee))
        if isinstance(getattr(decoratee, 'throttle', None), AsyncDecoration):
            decoratee.throttle = AsyncDecoration[Params, Return](decoratee=decoratee)
        decorated: AsyncDecorated[Params, Return] = decoratee

        return decorated


@dataclasses.dataclass(frozen=True)
class SyncDecorator(DecoratorData):

    def __call__[** Params, Return](
        self, decoratee: SyncDecoratee[Params, Return], /
    ) -> SyncDecorated[Params, Return]:
        decoratee = _context.SyncDecorator(self._prefix, self._suffix)(decoratee)
        decoratee.context.contexts.append(SyncContext(decoratee=decoratee))
        if not isinstance(getattr(decoratee, 'throttle', None), SyncDecoration):
            decoratee.throttle = SyncDecoration[Params, Return](decoratee=decoratee)
        decorated: SyncDecorated[Params, Return] = decoratee

        return decorated


@dataclasses.dataclass(frozen=True)
class Decorator(DecoratorData):

    @typing.overload
    def __call__[** Params, Return](
        self, decoratee: AsyncDecoratee[Params, Return], /
    ) -> AsyncDecorated[Params, Return]: ...

    @typing.overload
    def __call__[** Params, Return](
        self, decoratee: SyncDecoratee[Params, Return], /
    ) -> SyncDecorated[Params, Return]: ...

    def __call__[** Params, Return](self, decoratee: Decoratee[Params, Return], /) -> Decorated[Params, Return]:
        if inspect.iscoroutinefunction(decoratee):
            return AsyncDecorator(self._prefix, self._suffix)(decoratee)
        return SyncDecorator(self._prefix, self._suffix)(decoratee)
