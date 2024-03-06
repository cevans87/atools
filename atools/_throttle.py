import abc
import heapq
import inspect
import sys

import annotated_types
import asyncio
import dataclasses
import datetime
import threading
import time
import types
import typing

from . import _contexts

type Cond = asyncio.Condition | threading.Condition
type Lock = asyncio.Lock | threading.Lock
type Time = typing.Annotated[float, annotated_types.Ge(0.0)]


class Exception(_contexts.Exception):  # noqa
    ...


# TODO this whole class is a WIP
@dataclasses.dataclass(kw_only=True)
class AIMDSemaphore(abc.ABC):
    curr: typing.Annotated[int, annotated_types.Gt(0)]
    max_holders: typing.Annotated[int, annotated_types.Gt(0)]
    max_waiters: typing.Annotated[int, annotated_types.Gt(0)]
    penalty: Time | None = 0.0
    window: Time = 0.0

    holders: typing.Annotated[int, annotated_types.Ge(0)] = 0
    waiters: typing.Annotated[int, annotated_types.Ge(0)] = 0
    start_times: list[Time] = dataclasses.field(default_factory=list)
    cond: asyncio.Condition | threading.Condition

    @property
    def available(self) -> int:
        return self.curr - self.holders

    def _acquire_pre_wait(self) -> Cond | None:
        # Having max_holders/holders be a part of this check looks odd, but it averts a race condition where a lot of
        #  waiters have built up and would have immediately become holders if just given a moment. i.e., we only want to
        #  count waiters that are blocked waiting.
        if self.max_holders + self.max_waiters <= self.holders + self.waiters:
            raise Exception(f'Throttle max waiter limit {self.max_waiters} exceeded.')
        if (not self.waiters) and (self.holders < self.curr):
            return None

        self.waiters += 1
        return self.cond

    def _acquire_post_wait(self) -> None:
        self.waiters -= 1

    def _acquire_pre_delay(self) -> Time | None:
        self.holders += 1
        now = time.time()
        heapq.heappush(self.start_times, now)

        if len(self.start_times) > self.curr:
            heapq.heappop(self.start_times)

        if len(self.start_times) > self.curr and self.start_times[0] + self.window <= now:
            heapq.heappop(self.start_times)

        if len(self.start_times) >= self.max_holders - self.curr:
            return self.window - (now - heapq.heappop(self.start_times))

    def _acquire_post_delay(self) -> None:
        heapq.heappush(self.start_times, datetime.datetime.now())

    def _release(self, ok: bool) -> None:
        # FIXME wip
        match ok:
            case False if self.curr == 1:
                self.penalty = 1.0 if self.penalty is None else self.penalty * 2
            case False if self.curr <= self.holders * 2:
                self.curr //= 2

            case True if self.curr == 1:
                self.penalty = None
            case True if self.curr <= self.holders * 2:
                self.curr += 1

        self.holders -= 1
        if 0 < (available := self.curr - self.holders):
            self.cond.notify(available)


@dataclasses.dataclass(kw_only=True)
class AsyncAIMDSemaphore(AIMDSemaphore):
    cond: asyncio.Condition = dataclasses.field(default_factory=asyncio.Condition)

    async def acquire(self) -> None:
        async with self.cond:
            if (cond := self._acquire_pre_wait()) is not None:
                # FIXME: when curr goes negative, this breaks.
                await cond.wait_for(lambda: self.holders < self.curr)
                self._acquire_post_wait()

            delay = self._acquire_pre_delay()
        if delay is not None:
            await asyncio.sleep(delay)
            self._acquire_post_delay()

    async def release(self, ok: bool) -> None:
        async with self.cond:
            self._release(ok)


@dataclasses.dataclass(kw_only=True)
class MultiAIMDSemaphore(AIMDSemaphore):
    cond: threading.Condition = dataclasses.field(default_factory=threading.Condition)

    def acquire(self) -> None:
        with self.cond:
            if (cond := self._acquire_pre_wait()) is not None:
                cond.wait_for(lambda: self.holders < self.curr)
                self._acquire_post_wait()

            delay = self._acquire_pre_delay()
        if delay is not None:
            time.sleep(delay)
            self._acquire_post_delay()

    def release(self, ok: bool) -> None:
        with self.cond:
            self._release(ok)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](_contexts.Context, abc.ABC):
    begin: typing.Annotated[int, annotated_types.Gt(0)]
    max_holders: typing.Annotated[int, annotated_types.Gt(0)]
    max_waiters: typing.Annotated[int, annotated_types.Gt(0)]
    min_delay: datetime.timedelta
    semaphores: dict[typing.Hashable, AIMDSemaphore] = dataclasses.field(default_factory=dict)
    lock: Lock


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContext[** Params, Return](Context[Params, Return], _contexts.AsyncContext[Params, Return]):
    semaphores: dict[typing.Hashable, AsyncAIMDSemaphore] = dataclasses.field(default_factory=dict)
    lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)

    async def __call__(self) -> None: ...

    async def __aenter__(self):
        await self.semaphores.setdefault(
            self.key,
            AsyncAIMDSemaphore(curr=self.begin, max_holders=self.max_holders, max_waiters=self.max_waiters)
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
        match exc_type, exc_val, exc_tb:
            case None, None, None:
                await self.semaphores[self.key].release(ok=True)
            case _:
                await self.semaphores[self.key].release(ok=False)


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiContext[** Params, Return](Context[Params, Return], _contexts.MultiContext[Params, Return]):
    semaphores: dict[typing.Hashable, MultiAIMDSemaphore] = dataclasses.field(default_factory=dict)
    lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)

    def __call__(self, return_: Return) -> None: ...

    def __enter__(self):
        self.semaphores.setdefault(
            self.key,
            MultiAIMDSemaphore(curr=self.begin, max_holders=self.max_holders, max_waiters=self.max_waiters)
        ).acquire()
        return self

    @typing.overload
    def __exit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None: ...

    @typing.overload
    def __exit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None: ...

    def __exit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None:
        match exc_type, exc_val, exc_tb:
            case None, None, None:
                self.semaphores[self.key].release(ok=True)
            case _:
                self.semaphores[self.key].release(ok=False)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Decorator[** Params, Return]:
    begin: typing.Annotated[int, annotated_types.Gt(0)] = 1
    # How many callees are allowed through concurrently before additional callees become waiters.
    max_holders: typing.Annotated[int, annotated_types.Gt(0)] = sys.maxsize
    # How many callees are allowed through or to wait concurrently before additional callees are rejected.
    max_waiters: typing.Annotated[int, annotated_types.Gt(0)] = sys.maxsize
    # How many concurrent tokens to initialize with. This will never exceed given `soft` or `hard` values. Scaling
    #  follows AIMD control-flow rules. if this value is 1 and calls continue to fail, acquiring a token will incur an
    #  exponentially-increasing wait starting at 1 second before allowing the context to move forward.
    window: datetime.timedelta = datetime.timedelta(0)

    keygen: typing.Callable[Params, typing.Hashable] = lambda *args, **kwargs: None

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

        decorated = decoratee

        if inspect.iscoroutinefunction(decoratee):
            context = AsyncContext(
                begin=self.begin,
                max_holders=self.max_holders,
                max_waiters=self.max_waiters,
                min_delay=self.window,
                signature=inspect.signature(decoratee),
            )
        else:
            context = MultiContext(
                begin=self.begin,
                max_holders=self.max_holders,
                max_waiters=self.max_waiters,
                min_delay=self.window,
                signature=inspect.signature(decoratee),
            )

        decorated.contexts = tuple([context, *decorated.contexts])

        return decorated
