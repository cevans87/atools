import abc
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
type Lock = asyncio.Lock | threading.Lock
type Penalty = typing.Annotated[float, annotated_types.Gt(0.0)]
type Time = typing.Annotated[float, annotated_types.Gt(0.0)]


class Exception(_contexts.Exception):  # noqa
    ...


@dataclasses.dataclass(kw_only=True)
class AIMDSemaphore(abc.ABC):
    max_herd: int
    max_hold: int
    max_wait: int

    value: typing.Annotated[int, annotated_types.Gt(0)]
    window: typing.Annotated[float, annotated_types.Ge(0.0)]
    checkpoint: typing.Annotated[float, annotated_types.Ge(0.0)]

    n_herd: int = 0
    n_hold: int = 0
    n_wait: int = 0
    penalty: float = 0.0

    # TODO: Perhaps change this to a statically-sized list of _buckets_ or just a counter for start times in the last
    #  window. Growing and shrinking a heap will cause non-trivial overhead.
    condition: asyncio.Condition | threading.Condition

    def _acquire(self) -> typing.Generator[typing.Callable[[], typing.Awaitable[None] | None], None, None]:

        self.n_herd += 1
        while self.n_herd > self.max_herd:
            if self.n_herd > self.max_herd + 1:
                yield from self._wait_for(lambda: self.n_herd < self.max_herd)
            else:
                if (now := time.time()) < self.checkpoint:
                    yield lambda: self._sleep(self.checkpoint - now)
                self.checkpoint = self.checkpoint + (self.checkpoint - now) + self.window
                self.n_herd = 0
                self.condition.notify(min(self.n_wait, self.max_herd))
            self.n_herd += 1

        while self.n_hold >= self.value:
            yield from self._wait_for(lambda: self.n_hold < self.value)
        self.n_hold += 1

        if self.penalty:
            yield lambda: self._sleep(self.penalty)

    def _release(self, ok: bool) -> None:
        if ok:
            self.penalty = 0.0
            if self.n_hold > self.value // 2:
                self.value += 1
                self.condition.notify(1)
        elif 1 < self.value:
            self.value //= 2
        elif self.penalty:
            self.penalty *= 2
        else:
            self.penalty = 1.0

        self.n_hold -= 1
        if self.n_hold < self.value:
            self.condition.notify(1)

    @abc.abstractmethod
    def _sleep(self, time_: Time) -> typing.Awaitable[None] | None: ...

    def _wait_for(self, predicate: typing.Callable[[], bool]) -> None:
        if self.n_wait >= self.max_wait:
            raise Exception(f'{self.max_wait=} exceeded.')

        self.n_wait += 1
        try:
            yield lambda: self.condition.wait_for(predicate=predicate)
        finally:
            self.n_wait -= 1


@dataclasses.dataclass(kw_only=True)
class AsyncAIMDSemaphore(AIMDSemaphore):
    condition: asyncio.Condition = dataclasses.field(default_factory=lambda: asyncio.Condition())

    async def _sleep(self, penalty: Penalty) -> None:
        self.condition.release()
        try:
            await asyncio.sleep(penalty)
        finally:
            await self.condition.acquire()

    async def acquire(self) -> None:
        async with self.condition:
            for call in self._acquire():
                try:
                    await call()
                except TypeError as e:
                    raise

    async def release(self, ok: bool) -> None:
        async with self.condition:
            self._release(ok)


@dataclasses.dataclass(kw_only=True)
class MultiAIMDSemaphore(AIMDSemaphore):
    condition: threading.Condition = dataclasses.field(default_factory=lambda: threading.Condition())

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
    max_herd: int
    max_hold: int
    wait_hold: int
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
                checkpoint=time.time() + self.window,
                max_herd=self.max_herd,
                max_hold=self.max_hold,
                max_wait=self.wait_hold,
                value=self.start,
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
                checkpoint=time.time() + self.window,
                max_herd=self.max_herd,
                max_hold=self.max_hold,
                max_wait=self.wait_hold,
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
    max_herd: typing.Annotated[int, annotated_types.Gt(0)] = sys.maxsize

    # How many callees are allowed through concurrently before additional callees become waiters.
    max_hold: typing.Annotated[int, annotated_types.Gt(0)] = sys.maxsize

    # How many callees are allowed through or to wait concurrently before additional callees are rejected.
    wait_hold: typing.Annotated[int, annotated_types.Gt(0)] = sys.maxsize

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
                max_herd=self.max_herd,
                max_hold=self.max_hold,
                wait_hold=self.wait_hold,
                signature=inspect.signature(decoratee),
                start=self.start,
                window=self.window,
            )
        else:
            context = MultiContext(
                keygen=self.keygen,
                max_herd=self.max_herd,
                max_hold=self.max_hold,
                wait_hold=self.wait_hold,
                signature=inspect.signature(decoratee),
                start=self.start,
                window=self.window,
            )

        decoratee.contexts = tuple([context, *decoratee.contexts])

        decorated = decoratee

        return decorated
