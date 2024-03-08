import abc
import builtins
import functools
import contextlib
import dataclasses
import inspect
import types
import typing


class Exception(builtins.Exception):  # noqa
    ...


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
    signature: inspect.Signature

    @property
    def key(self):
        assert self.args is not ... and self.kwargs is not ...

        bound_arguments = self.signature.bind(*self.args, **self.kwargs)
        bound_arguments.apply_defaults()

        return bound_arguments.args, tuple(sorted(bound_arguments.kwargs.items()))


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContext[** Params, Return](Context[Params, Return], abc.ABC):
    async def __call__(self) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None:
        return None


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiContext[** Params, Return](Context[Params, Return], abc.ABC):

    def __call__(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None:
        return None


@dataclasses.dataclass(kw_only=True)
class Decorated[** Params, Return](abc.ABC):
    contexts: tuple[Context[Params, Return], ...] = ()
    decoratee: Decoratee[Params, Return]

    __call__: typing.ClassVar[typing.Callable[Params, typing.Awaitable[Return] | Return]]


@dataclasses.dataclass(kw_only=True)
class AsyncDecorated[** Params, Return](Decorated[Params, Return]):
    contexts: tuple[AsyncContext[Params, Return], ...] = ()
    decoratee: AsyncDecoratee[Params, Return]

    async def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return:
        async with contextlib.AsyncExitStack() as stack:
            for context in self.contexts:
                await stack.enter_async_context(dataclasses.replace(context, args=args, kwargs=kwargs))

            return_ = await self.decoratee(*args, **kwargs)

            for context in reversed(self.contexts):
                await dataclasses.replace(context, args=args, kwargs=kwargs, return_=return_)()

        return return_


@dataclasses.dataclass(kw_only=True)
class MultiDecorated[** Params, Return](Decorated[Params, Return]):
    contexts: tuple[MultiContext[Params, Return], ...] = ()
    decoratee: MultiDecoratee[Params, Return]

    def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return:
        with contextlib.ExitStack() as stack:
            for context in self.contexts:
                stack.enter_context(dataclasses.replace(context, args=args, kwargs=kwargs))

            return_ = self.decoratee(*args, **kwargs)

            for context in reversed(self.contexts):
                dataclasses.replace(context, args=args, kwargs=kwargs, return_=return_)()

        return return_


@dataclasses.dataclass(frozen=True)
class Decorator[** Params, Return]:

    @typing.overload
    def __call__(self, decoratee: AsyncDecoratee[Params, Return], /) -> AsyncDecorated[Params, Return]: ...

    @typing.overload
    def __call__(self, decoratee: MultiDecoratee[Params, Return], /) -> MultiDecorated[Params, Return]: ...

    def __call__(self, decoratee: Decoratee, /) -> Decorated:
        assert not isinstance(decoratee, Context)

        if inspect.iscoroutinefunction(decoratee):
            decorated = inspect.markcoroutinefunction(AsyncDecorated(decoratee=decoratee))
        else:
            decorated = MultiDecorated(decoratee=decoratee)
        decorated = functools.wraps(decoratee)(decorated)

        assert isinstance(decorated, Decorated)

        return decorated
