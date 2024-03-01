import annotated_types
import asyncio
import collections
import dataclasses
import datetime
import threading
import types
import typing

from . import _contexts

# Usage of Semaphore over BoundedSemaphore is intentional. Under AIMD behavior, we add additional tokens when there are
#  waiters and a token-holder succeeds.
type Semaphore = asyncio.Semaphore | threading.Semaphore


class Context[** Params, Return](_contexts.Context):
    limit: int
    tokens: dict[typing.Hashable, Semaphore] = dataclasses.field(default_factory=dict)


class AsyncContext[** Params, Return](Context[Params, Return], _contexts.AsyncContext[Params, Return]):
    key: typing.Hashable = ...
    tokens: dict[typing.Hashable, asyncio.Semaphore]

    async def __call__(self, return_: Return) -> None:
        ...

    async def __aenter__(self):
        await self.tokens[self.key].acquire()
        return self

    async def __aexit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None:
        self.tokens[self.key].release()
        return None


class MultiContext[** Params, Return](Context[Params, Return], _contexts.MultiContext[Params, Return]):
    key: typing.Hashable
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
    # TODO: change this to an optional positional (i.e. ...) and allow AIMD control-flow behavior.
    # How many callees are allowed through concurrently before additional callees become waiters.
    _soft: typing.Annotated[int, annotated_types.Gt(0)]

    # How many callees are allowed through or to wait concurrently before additional callees are rejected.
    _hard: typing.Annotated[int, annotated_types.Gt(0)] = ...

    _: dataclasses.KW_ONLY = ...
    aimd: bool = False
    keygen: typing.Callable[Params, typing.Hashable] = lambda *args, **kwargs: None
    timeout: datetime.timedelta | None = None
    window: datetime.timedelta = datetime.timedelta(seconds=1)

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

        return decorated
