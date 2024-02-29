import abc
import functools
import contextlib
import dataclasses
import inspect
import types
import typing


class Decoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, typing.Awaitable[Return] | Return]


class AsyncDecoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, typing.Awaitable[Return]]


class MultiDecoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, Return]


@typing.final
@dataclasses.dataclass(frozen=True, kw_only=True)
class State[** Params, Return]:
    args: Params.args = ...
    kwargs: Params.kwargs = ...
    return_: Return = ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class Decoration[** Params, Return](abc.ABC):
    state: State[Params, Return]


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncDecoration[** Params, Return](Decoration[Params, Return], abc.ABC):
    __call__: typing.Callable[[Return], typing.Awaitable[Return]] = ...

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None:
        return None


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiDecoration[** Params, Return](Decoration[Params, Return], abc.ABC):
    __call__: typing.Callable[[Return], Return] = ...

    def __enter__(self):
        return self

    def __exit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None:
        return None


@typing.runtime_checkable
class Decorated[** Params, Return](typing.Protocol):
    decoratee: Decoratee[Params, Return]
    decorations: tuple[Decoration[Params, Return], ...]
    __call__: typing.Callable[Params, typing.Awaitable[Return] | Return]


@typing.runtime_checkable
class AsyncDecorated[** Params, Return](Decorated[Params, Return], typing.Protocol):
    decoratee: AsyncDecoratee[Params, Return]
    decorations: tuple[AsyncDecoration[Params, Return], ...]
    __call__: typing.Callable[Params, typing.Awaitable[Return]]


@typing.runtime_checkable
class MultiDecorated[** Params, Return](Decorated[Params, Return], typing.Protocol):
    decoratee: MultiDecoratee[Params, Return]
    decorations: tuple[MultiDecoration[Params, Return], ...]
    __call__: typing.Callable[Params, typing.Awaitable[Return]]


@dataclasses.dataclass(frozen=True)
class Decorator[** Params, Return]:

    @typing.overload
    def __call__(self, decoratee: AsyncDecoratee[Params, Return], /) -> AsyncDecorated[Params, Return]: ...

    @typing.overload
    def __call__(self, decoratee: MultiDecoratee[Params, Return], /) -> MultiDecorated[Params, Return]: ...

    def __call__(self, decoratee: Decoratee, /) -> Decorated:
        assert not isinstance(decoratee, Decoration)

        decoratee.decoratee = decoratee
        decoratee.decorations = tuple()
        assert isinstance(decoratee, Decorated)

        if inspect.iscoroutinefunction(decoratee):
            @functools.wraps(decoratee)
            async def decoratee(*args: Params.args, **kwargs: Params.kwargs) -> Return:
                async with contextlib.AsyncExitStack() as stack:
                    decorations = [
                        await stack.enter_async_context(
                            dataclasses.replace(decoration, state=State(args=args, kwargs=kwargs)))
                        for decoration in reversed(decoratee.decorations)
                    ]

                    return_ = await decoratee.decoratee(*args, **kwargs)

                    for decoration in reversed(decorations):
                        await decoration(State(args=args, kwargs=kwargs, return_=return_))

                return return_

            assert isinstance(decoratee, AsyncDecorated)
        else:
            @functools.wraps(decoratee)
            def decoratee(*args: Params.args, **kwargs: Params.kwargs) -> Return:
                with contextlib.ExitStack() as stack:
                    decorations = [
                        stack.enter_context(dataclasses.replace(decoration, state=State(args=args, kwargs=kwargs)))
                        for decoration in reversed(decoratee.decorations)
                    ]

                    return_ = decoratee.decoratee(*args, **kwargs)

                    for decoration in reversed(decorations):
                        decoration(State(args=args, kwargs=kwargs, return_=return_))

                return return_

            assert isinstance(decoratee, MultiDecorated)

        decorated = decoratee

        return decorated
