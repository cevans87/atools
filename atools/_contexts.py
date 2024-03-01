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


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](abc.ABC):
    args: Params.args = ...
    kwargs: Params.kwargs = ...
    return_: Return = ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContext[** Params, Return](Context[Params, Return], abc.ABC):
    __call__: typing.Callable[[Return], typing.Awaitable[None]] = ...

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None:
        return None


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiContext[** Params, Return](Context[Params, Return], abc.ABC):
    __call__: typing.Callable[[Return], None] = ...

    def __enter__(self):
        return self

    def __exit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None:
        return None


@typing.runtime_checkable
class Decorated[** Params, Return](typing.Protocol):
    contexts: tuple[Context[Params, Return], ...]
    __call__: typing.Callable[Params, typing.Awaitable[Return] | Return]
    __wrapped__: Decoratee[Params, Return]


@typing.runtime_checkable
class AsyncDecorated[** Params, Return](Decorated[Params, Return], typing.Protocol):
    contexts: tuple[AsyncContext[Params, Return], ...]
    __call__: typing.Callable[Params, typing.Awaitable[Return]]
    __wrapped__: AsyncDecoratee[Params, Return]


@typing.runtime_checkable
class MultiDecorated[** Params, Return](Decorated[Params, Return], typing.Protocol):
    contexts: tuple[MultiContext[Params, Return], ...]
    __call__: typing.Callable[Params, typing.Awaitable[Return]]
    __wrapped__: MultiDecoratee[Params, Return]


@dataclasses.dataclass(frozen=True)
class Decorator[** Params, Return]:

    @typing.overload
    def __call__(self, decoratee: AsyncDecoratee[Params, Return], /) -> AsyncDecorated[Params, Return]: ...

    @typing.overload
    def __call__(self, decoratee: MultiDecoratee[Params, Return], /) -> MultiDecorated[Params, Return]: ...

    def __call__(self, decoratee: Decoratee, /) -> Decorated:
        assert not isinstance(decoratee, Context)
        decoratee.contexts = tuple()

        if inspect.iscoroutinefunction(decoratee):
            @functools.wraps(decoratee)
            async def decorated(*args: Params.args, **kwargs: Params.kwargs) -> Return:
                async with contextlib.AsyncExitStack() as stack:
                    for context in decoratee.contexts:
                        await stack.enter_async_context(dataclasses.replace(context, args=args, kwargs=kwargs))

                    return_ = await decoratee(*args, **kwargs)

                    for context in reversed(decoratee.contexts):
                        await context.replace(args=args, kwargs=kwargs, return_=return_)()

                return return_

            assert isinstance(decorated, AsyncDecorated)
        else:
            @functools.wraps(decoratee)
            def decorated(*args: Params.args, **kwargs: Params.kwargs) -> Return:
                with contextlib.ExitStack() as stack:

                    for context in decoratee.contexts:
                        stack.enter_context(dataclasses.replace(context, args=args, kwargs=kwargs))

                    return_ = decoratee(*args, **kwargs)

                    for context in reversed(decoratee.contexts):
                        context.replace(args=args, kwargs=kwargs, return_=return_)()

                return return_

            assert isinstance(decorated, MultiDecorated)

        return decorated
