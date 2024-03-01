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
    base: tuple[Decoration[Params, Return], ...]
    __call__: typing.Callable[Params, typing.Awaitable[Return] | Return]
    __wrapped__: Decoratee[Params, Return]


@typing.runtime_checkable
class AsyncDecorated[** Params, Return](Decorated[Params, Return], typing.Protocol):
    base: tuple[AsyncDecoration[Params, Return], ...]
    __call__: typing.Callable[Params, typing.Awaitable[Return]]
    __wrapped__: AsyncDecoratee[Params, Return]


@typing.runtime_checkable
class MultiDecorated[** Params, Return](Decorated[Params, Return], typing.Protocol):
    base: tuple[MultiDecoration[Params, Return], ...]
    __call__: typing.Callable[Params, typing.Awaitable[Return]]
    __wrapped__: MultiDecoratee[Params, Return]


@dataclasses.dataclass(frozen=True)
class Decorator[** Params, Return]:

    @typing.overload
    def __call__(self, decoratee: AsyncDecoratee[Params, Return], /) -> AsyncDecorated[Params, Return]: ...

    @typing.overload
    def __call__(self, decoratee: MultiDecoratee[Params, Return], /) -> MultiDecorated[Params, Return]: ...

    def __call__(self, decoratee: Decoratee, /) -> Decorated:
        assert not isinstance(decoratee, Decoration)
        decoratee.base = tuple()

        if inspect.iscoroutinefunction(decoratee):
            @functools.wraps(decoratee)
            async def decorated(*args: Params.args, **kwargs: Params.kwargs) -> Return:
                async with contextlib.AsyncExitStack() as stack:
                    base = [
                        await stack.enter_async_context(
                            dataclasses.replace(decoration, state=State(args=args, kwargs=kwargs)))
                        for decoration in reversed(decoratee.base)
                    ]

                    return_ = await decoratee(*args, **kwargs)

                    for decoration in reversed(base):
                        await decoration(State(args=args, kwargs=kwargs, return_=return_))

                return return_

            assert isinstance(decorated, AsyncDecorated)
        else:
            @functools.wraps(decoratee)
            def decorated(*args: Params.args, **kwargs: Params.kwargs) -> Return:
                with contextlib.ExitStack() as stack:
                    base = [
                        stack.enter_context(dataclasses.replace(decoration, state=State(args=args, kwargs=kwargs)))
                        for decoration in reversed(decoratee.base)
                    ]

                    return_ = decoratee(*args, **kwargs)

                    for decoration in reversed(base):
                        decoration(State(args=args, kwargs=kwargs, return_=return_))

                return return_

            assert isinstance(decorated, MultiDecorated)

        return decorated
