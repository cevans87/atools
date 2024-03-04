import inspect

import annotated_types
import asyncio
import dataclasses
import datetime
import inspect
import threading
import types
import typing

from . import _contexts

# Usage of Semaphore over BoundedSemaphore is intentional. Under AIMD behavior, we add additional tokens when there are
#  waiters and a token-holder succeeds.
type Semaphore = asyncio.Semaphore | threading.Semaphore


kwd_mark = object()


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](_contexts.Context):
    key: typing.Hashable
    limit: int
    tokens: dict[typing.Hashable, Semaphore] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.args is ... or self.kwargs is ... or self.key is not ...:
            return

        object.__setattr__(self, 'key', tuple([*self.args, kwd_mark, *tuple(sorted(self.kwargs.items))]))

    def __hash__(self) -> typing.Hashable:
        return tuple([*self.args, kwd_mark, *tuple(sorted(self.kwargs.items))])


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContext[** Params, Return](Context[Params, Return], _contexts.AsyncContext[Params, Return]):
    tokens: dict[typing.Hashable, asyncio.Semaphore]

    async def __call__(self, return_: Return) -> None:
        ...

    async def __aenter__(self):
        await self.tokens.setdefault(self.key, asyncio.Semaphore()).acquire()
        return self

    async def __aexit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None:
        self.tokens[self.key].release()
        return None


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiContext[** Params, Return](Context[Params, Return], _contexts.MultiContext[Params, Return]):
    tokens: dict[typing.Hashable, threading.Semaphore] = ...

    def __call__(self, return_: Return) -> None:
        ...

    def __enter__(self):
        self.tokens[self.key].acquire()
        return self

    def __exit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None:
        self.tokens[self.key].release()
        return None


@dataclasses.dataclass(frozen=True, kw_only=True)
class Decorator[** Params, Return]:
    # How many callees are allowed through concurrently before additional callees become waiters.
    soft: typing.Annotated[int, annotated_types.Gt(0)] = ...
    # How many callees are allowed through or to wait concurrently before additional callees are rejected.
    hard: typing.Annotated[int, annotated_types.Gt(0)] = ...
    # How many concurrent tokens to initialize with. This will never exceed given `soft` or `hard` values. Scaling
    #  follows AIMD control-flow rules. if this value is 1 and calls continue to fail, acquiring a token will incur an
    #  exponentially-increasing wait starting at 1 second before allowing the context to move forward.
    begin: typing.Annotated[int, annotated_types.Gt(0)] = ...

    keygen: typing.Callable[Params, typing.Hashable] = lambda *args, **kwargs: None
    window: datetime.timedelta = ...

    @typing.overload
    def __call__(
        self, decoratee: _contexts.AsyncDecoratee[Params, Return], /
    ) -> _contexts.AsyncDecorated[Params, Return]: ...

    @typing.overload
    def __call__(
        self, decoratee: _contexts.MultiDecoratee[Params, Return], /
    ) -> _contexts.MultiDecorated[Params, Return]: ...

    def __call__(
        self, decoratee: _contexts.Decoratee[Params, Return]
    ) -> _contexts.Decorated[Params, Return]:
        if not isinstance(decoratee, _contexts.Decorated):
            decoratee = _contexts.Decorator[Params, Return](decoratee)

        decorated = decoratee

        # TODO add our context to the decorated.contexts

        return decorated
