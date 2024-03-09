import abc
import collections
import contextlib
import inspect
import sys

import annotated_types
import asyncio
import dataclasses
import threading
import time
import types
import typing

from . import _contexts

type Condition = asyncio.Condition | threading.Condition
type Heap[T] = list[T]
type History = collections.deque[tuple[Time, typing.Annotated, annotated_types.Ge(0)]]
type Lock = asyncio.Lock | threading.Lock
type Penalty = typing.Annotated[float, annotated_types.Gt(0.0)]
type Pause = typing.Annotated[float, annotated_types.Gt(0.0)]
type Time = typing.Annotated[float, annotated_types.Gt(0.0)]

type EndFrame = typing.Annotated[float, annotated_types.Gt(0.0)]
type Window = typing.Annotated[float, annotated_types.Gt(0.0)]


class Exception(_contexts.Exception):  # noqa
    ...


@dataclasses.dataclass(kw_only=True)
class AIMDSemaphore(abc.ABC):

    hi: int
    lo: int
    hold: int = ...
    value: int
    window: typing.Annotated[float, annotated_types.Ge(0.0)]

    penalty: float = 0.0
    checkpoint: float = 0.0

    # TODO: Perhaps change this to a statically-sized list of _buckets_ or just a counter for start times in the last
    #  window. Growing and shrinking a heap will cause non-trivial overhead.
    condition: asyncio.Condition | threading.Condition

    def __post_init__(self) -> None:
        self.hold = self.hi - self.value
        self.checkpoint = time.time() + self.window

    def _acquire(self) -> typing.Generator[typing.Callable[[], typing.Awaitable[None] | None], None, None]:
        self.value -= 1

        if 0 <= self.value:
            pass
        elif self.value < self.lo:
            raise Exception(f'Throttle minimum {self.lo} exceeded.')
        elif not self.window:
            yield lambda: self.condition.wait_for(lambda: 0 <= self.value)
        else:
            if (now := time.time()) < self.checkpoint:
                yield lambda: self._sleep(self.checkpoint - now)
                self.hold -= 1 if self.hold else 0
            self.checkpoint = max(now, self.checkpoint) + self.window
            self.value = self.hi - self.hold

        if self.penalty:
            yield lambda: self._sleep(self.penalty)

    def _release(self, ok: bool) -> None:
        if self.window:
            return

        self.value += 1
        self.condition.notify(1)

        if ok:
            self.penalty = 0.0
            if self.hi - self.hold - max(0, self.value) <= max(0, self.value):
                self.value += 1
                self.hold -= 1
                self.condition.notify(1)
        elif self.penalty:
            self.penalty *= 2
        elif self.hold == self.hi:
            self.penalty = 1.0
        elif self.penalty:
            self.penalty *= 2
        else:
            exchange = (self.hi - self.hold) // 2
            self.hold += exchange
            self.value -= exchange

    @abc.abstractmethod
    def _sleep(self, time_: Time) -> typing.Awaitable[None] | None: ...


@dataclasses.dataclass(kw_only=True)
class AsyncAIMDSemaphore(AIMDSemaphore):
    condition: asyncio.Condition = dataclasses.field(default_factory=asyncio.Condition)

    async def _sleep(self, penalty: Penalty) -> None:
        self.condition.release()
        try:
            await asyncio.sleep(penalty)
        finally:
            await self.condition.acquire()

    async def acquire(self) -> None:
        async with self.condition:
            for call in self._acquire():
                await call()

    async def release(self, ok: bool) -> None:
        async with self.condition:
            self._release(ok)


@dataclasses.dataclass(kw_only=True)
class MultiAIMDSemaphore(AIMDSemaphore):
    condition: threading.Condition = dataclasses.field(default_factory=threading.Condition)

    def _sleep(self, time_: Time) -> None:
        self.condition.release()
        try:
            time.sleep(time_)
        finally:
            self.condition.acquire()

    def acquire(self) -> None:
        with self.condition:
            for call in self._acquire():
                call()

    def release(self, ok: bool) -> None:
        with self.condition:
            self._release(ok)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](_contexts.Context, abc.ABC):
    keygen: typing.Callable[Params, typing.Hashable]
    lock: dataclasses.Field[Lock]
    hi: int
    lo: int
    start: int
    window: typing.Annotated[float, annotated_types.Ge(0.0)]
    semaphores: dict[typing.Hashable, AIMDSemaphore]


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContext[** Params, Return](Context[Params, Return], _contexts.AsyncContext[Params, Return]):
    lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)
    semaphores: dict[typing.Hashable, AsyncAIMDSemaphore] = dataclasses.field(default_factory=dict)

    async def __aenter__(self):
        await self.semaphores.setdefault(
            self.keygen(*self.args, **self.kwargs),
            AsyncAIMDSemaphore(
                hi=self.hi,
                value=self.start,
                lo=self.lo,
                window=self.window,
            )
        ).acquire()
        return self

    @typing.overload
    async def __aexit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None: ...

    @typing.overload
    async def __aexit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: object | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        async with self.lock:
            semaphore = self.semaphores[self.keygen(*self.args, **self.kwargs)]
        match exc_type, exc_val, exc_tb:
            case None, None, None:
                await semaphore.release(ok=True)
            case _:
                await semaphore.release(ok=False)


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiContext[** Params, Return](Context[Params, Return], _contexts.MultiContext[Params, Return]):
    lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    semaphores: dict[typing.Hashable, MultiAIMDSemaphore] = dataclasses.field(default_factory=dict)

    def __enter__(self):
        self.semaphores.setdefault(
            self.keygen(*self.args, **self.kwargs),
            MultiAIMDSemaphore(
                hi=self.hi,
                lo=self.lo,
                value=self.start,
                window=self.window,
            )
        ).acquire()
        return self

    @typing.overload
    def __exit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None: ...

    @typing.overload
    def __exit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None: ...

    def __exit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None:
        with self.lock:
            semaphore = self.semaphores[self.keygen(*self.args, **self.kwargs)]
        match exc_type, exc_val, exc_tb:
            case None, None, None:
                semaphore.release(ok=True)
            case _:
                semaphore.release(ok=False)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Decorator[** Params, Return]:
    # TODO: make a sync and async version of the key return.
    keygen: typing.Callable[Params, typing.Hashable] = lambda *args, **kwargs: None
    # How many callees are allowed through concurrently before additional callees become waiters.
    hi: typing.Annotated[int, annotated_types.Gt(0)] = sys.maxsize

    # How many callees are allowed through or to wait concurrently before additional callees are rejected.
    lo: typing.Annotated[int, annotated_types.Le(0)] = -sys.maxsize - 1

    # How many concurrent tokens to initialize with. This will never exceed given `soft` or `hard` values. Scaling
    #  follows AIMD control-flow rules. if this value is 1 and calls continue to fail, acquiring a token will incur an
    #  exponentially-increasing wait starting at 1 second before allowing the context to move forward.
    start: typing.Annotated[int, annotated_types.Gt(0)] = 1
    window: typing.Annotated[float, annotated_types.Ge(0.0)] = 0.0

    Exception: typing.ClassVar = Exception

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
            decoratee = _contexts.Decorator[Params, Return]()(decoratee)

        if inspect.iscoroutinefunction(decoratee):
            context = AsyncContext(
                keygen=self.keygen,
                hi=self.hi,
                lo=self.lo,
                signature=inspect.signature(decoratee),
                start=self.start,
                window=self.window,
            )
        else:
            context = MultiContext(
                keygen=self.keygen,
                hi=self.hi,
                lo=self.lo,
                signature=inspect.signature(decoratee),
                start=self.start,
                window=self.window,
            )

        decoratee.contexts = tuple([context, *decoratee.contexts])

        decorated = decoratee

        return decorated
