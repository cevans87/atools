from __future__ import annotations
import abc
import contextlib
import dataclasses
import functools
import inspect
import typing

from . import _key


@dataclasses.dataclass(frozen=True, kw_only=True)
class ContextBase[** Params, Return](abc.ABC):
    args: list[object]
    kwargs: dict[str, object]


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContext[** Params, Return](ContextBase[Params, Return], abc.ABC):
    __call__: typing.Callable[[Return], typing.Awaitable[None]]


@dataclasses.dataclass(frozen=True, kw_only=True)
class SyncContext[** Params, Return](ContextBase[Params, Return], abc.ABC):
    __call__: typing.Callable[[Return], None]


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContextManager[** Params, Return](contextlib.AbstractAsyncContextManager, abc.ABC):
    decorated: Decorated[Params, typing.Awaitable[Return]]
    context_managers: tuple[AsyncContextManager, ...]

    __call__: typing.Callable[[typing.Self, Return, Params], typing.Awaitable[None]]


@dataclasses.dataclass(frozen=True, kw_only=True)
class SyncContextManager[** Params, Return](contextlib.AbstractContextManager, abc.ABC):
    decorated: Decorated[Params, Return]
    context_managers: tuple[SyncContextManager, ...]

    __call__: typing.Callable[[typing.Self, Return, Params], None]


class AsyncDecoration[** Params, Return]:
    decoratee: AsyncDecoratee[Params, Return]
    context_managers: list[AsyncContextManager]


class SyncDecoration[** Params, Return]:
    decoratee: SyncDecoratee[Params, Return]
    context_managers: list[SyncContextManager]

    def __call__(self, *args, **kwargs) -> Return:
        ...


class AsyncDecoratee[** Params, Return](typing.Protocol):
    __call__:typing.Callable[Params, typing.Awaitable[Return]]


class SyncDecoratee[** Params, Return](typing.Protocol):
    __call__:typing.Callable[Params, Return]


type Decoratee[** Params, Return] = AsyncDecoratee[Params, Return] | SyncDecoratee[Params, Return]


class AsyncDecorated[** Params, Return](AsyncDecoratee[Params, Return], _key.Decorated):
    context: AsyncDecoration[Params, Return]


class SyncDecorated[** Params, Return](SyncDecoratee[Params, Return], _key.Decorated):
    context: SyncDecoration[Params, Return]


type Decorated[** Params, Return] = AsyncDecorated[Params, Return] | SyncDecorated[Params, Return]


@dataclasses.dataclass(frozen=True, init=False)
class Decorator[Params, Return]:
    prefix: _key.Name = ...
    suffix: _key.Name = ...

    AsyncContextManager: typing.ClassVar[type[AsyncContextManager]] = AsyncContextManager
    SyncContextManager: typing.ClassVar[type[SyncContextManager]] = SyncContextManager

    def __init__(self, _name: _key.Name = ..., /, *, prefix: _key.Name = ..., suffix: _key.Name = ...) -> None:
        object.__setattr__(self, 'prefix', prefix)
        object.__setattr__(self, 'suffix', suffix)

    @typing.overload
    def __call__[** Params, Return](
        self, decoratee: AsyncDecoratee[Params, Return], /
    ) -> AsyncDecorated[Params, Return]: ...

    @typing.overload
    def __call__[** Params, Return](
        self, decoratee: SyncDecoratee[Params, Return], /
    ) -> SyncDecorated[Params, Return]: ...

    def __call__[** Params, Return](self, decoratee: Decorated[Params, Return], /) -> Decorated[Params, Return]:
        if isinstance(getattr(decoratee, 'wrap', None), (AsyncDecoration, SyncDecoration)):
            decoratee: Decorated[Params, Return]
            return decoratee

        if inspect.iscoroutinefunction(decoratee):
            decoratee.wrap = AsyncDecoration[Params, Return](decoratee=decoratee)
            decorated: AsyncDecoratee[Params, Return] = decoratee

            async def decorated(*args, **kwargs) -> Return:
                async with contextlib.AsyncExitStack() as stack:
                    for context_manager in reversed(decoratee.context.context_managers):
                        await stack.enter_async_context(context_manager)

                    return_ = await decoratee(*args, **kwargs)

                    for context_manager in decoratee.context.context_managers:
                        await context_manager(return_, *args, **kwargs)

                return return_

        else:
            decoratee.context = SyncDecoration[Params, Return](decoratee=decoratee)
            decorated: SyncDecorated[Params, Return] = decoratee

            def decorated(*args, **kwargs) -> Return:
                with contextlib.ExitStack() as stack:
                    for context_manager in reversed(decorated.context.context_managers):
                        stack.enter_context(context_manager)

                    return_ = decoratee(*args, **kwargs)

                    for context_manager in decoratee.context.context_managers:
                        context_manager(return_, *args, **kwargs)

                return return_

        return functools.wraps(decoratee)(decorated)
