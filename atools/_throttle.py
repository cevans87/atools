import abc
import annotated_types
import asyncio
import dataclasses
import heapq
import inspect
import sys
import threading
import time
import types
import typing

from . import _base

type Condition = asyncio.Condition | threading.Condition
type Lock = asyncio.Lock | threading.Lock
type Penalty = typing.Annotated[float, annotated_types.Gt(0.0)]
type Time = typing.Annotated[float, annotated_types.Gt(0.0)]


class Exception(_base.Exception):  # noqa
    ...


@dataclasses.dataclass(kw_only=True)
class AIMDSemaphore(abc.ABC):
    """Semaphore with AIMD behavior.

    Definitions:
        - hold - Callers that have acquired a semaphore value but have not released.
        - unit - Callers that `hold` and are allowed to begin execution within the current temporal `slice`.
        - wait - Callers that are waiting because the `max_herd` or `max_hold` limit would be exceeded.

        - slice - Discreet temporal checkpoint after which another `max_units` units are allowed through.
        - window - The amount of time that must pass after an individual slice expires before it is replenished.

    'value' behavior:
        - No more than the current `value` callers are approved to `hold`.
        - Value increases by 1 if a holder releases without raising an exception and the number of holders is greater
          than half of value.

    'checkpoint' behavior:
        -

    Value
    """
    max_holds: int
    max_panes: int
    max_units: int
    max_waits: int

    value: int
    window: typing.Annotated[float, annotated_types.Ge(0.0)]

    holds: int = 0
    panes: list[float] = dataclasses.field(default_factory=list)
    units: int = 0
    waits: int = 0

    units_pending = False

    holds_condition: asyncio.Condition | threading.Condition
    units_condition: asyncio.Condition | threading.Condition

    def __post_init__(self) -> None:
        self.units = self.max_units

    def _acquire_hold(self) -> typing.Generator[typing.Callable[[], typing.Awaitable[None] | None], None, None]:
        while self.holds >= max(1, self.value):
            yield from self._wait(self.holds_condition)
        self.holds += 1

        if self.value <= 0:
            yield lambda: self._sleep(self.holds_condition, 2.0 ** -self.value)

    def _acquire_unit(self) -> typing.Generator[typing.Callable[[], typing.Awaitable[None] | None], None, None]:
        while self.units >= self.max_units:
            if self.units_pending:
                yield from self._wait(self.units_condition)
            elif not self.panes:
                self.units = 0
                heapq.heappush(self.panes, time.time() + self.window)
            elif self.panes[0] < (now := time.time()):
                self.units = 0
                heapq.heappushpop(self.panes, now + self.window)
            elif len(self.panes) < self.max_panes:
                self.units = 0
                heapq.heappush(self.panes, now + self.window)
            else:
                self.units_pending = True
                yield lambda: self._sleep(self.units_condition, self.panes[0] - now)
                self.units_pending = False
                self.units = 0
                heapq.heappushpop(self.panes, self.panes[0] + self.window)
                self.units_condition.notify(self.max_units + 1)
        self.units += 1

    def _release(self, ok: bool) -> None:
        match ok:
            case True if self.value <= 0:
                self.value = 1
            case True if self.holds in range((self.value // 2) + 1, self.max_holds):
                self.value += 1
                self.holds_condition.notify(1)
            case False if self.value > 0:
                self.value //= 2
            case False:
                self.value -= 1

        self.holds -= 1
        self.holds_condition.notify(1)

    @abc.abstractmethod
    def _sleep(self, condition: asyncio.Condition | threading.Condition, time_: Time) -> typing.Awaitable[None] | None:
        raise NotImplemented

    def _wait(self, condition: asyncio.Condition | threading.Condition) -> None:
        if self.waits >= self.max_waits:
            raise Exception(f'{self.max_waits=} exceeded.')

        self.waits += 1
        try:
            yield lambda: condition.wait()
        finally:
            self.waits -= 1

    def _wait_for(
        self, condition: asyncio.Condition | threading.Condition, predicate: typing.Callable[[], bool]
    ) -> typing.Generator[typing.Callable[[], typing.Awaitable[None] | None], None, None]:
        if self.waits >= self.max_waits:
            raise Exception(f'{self.max_waits=} exceeded.')

        self.waits += 1
        try:
            yield lambda: condition.wait_for(predicate=predicate)
        finally:
            self.waits -= 1


@dataclasses.dataclass(kw_only=True)
class AsyncAIMDSemaphore(AIMDSemaphore):
    holds_condition: asyncio.Condition = dataclasses.field(default_factory=lambda: asyncio.Condition())
    units_condition: asyncio.Condition = dataclasses.field(default_factory=lambda: asyncio.Condition())

    async def _sleep(self, condition: asyncio.Condition, delay: float) -> None:
        condition.release()
        try:
            await asyncio.sleep(delay)
        finally:
            await condition.acquire()

    async def acquire(self) -> None:
        async with self.holds_condition:
            for call in self._acquire_hold():
                await call()
        async with self.units_condition:
            for call in self._acquire_unit():
                await call()

    async def release(self, ok: bool) -> None:
        async with self.holds_condition:
            self._release(ok)


@dataclasses.dataclass(kw_only=True)
class MultiAIMDSemaphore(AIMDSemaphore):
    holds_condition: threading.Condition = dataclasses.field(default_factory=lambda: threading.Condition())
    units_condition: threading.Condition = dataclasses.field(default_factory=lambda: threading.Condition())

    def _sleep(self, condition: threading.Condition, delay: float) -> None:
        condition.release()
        try:
            time.sleep(delay)
        finally:
            condition.acquire()

    def acquire(self) -> None:
        with self.holds_condition:
            for call in self._acquire_hold():
                call()
        with self.units_condition:
            for call in self._acquire_unit():
                call()

    def release(self, ok: bool) -> None:
        with self.holds_condition:
            self._release(ok)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](_base.Context, abc.ABC):
    keygen: typing.Callable[Params, typing.Hashable]
    lock: dataclasses.Field[Lock]
    max_holds: int
    max_panes: int
    max_units: int
    max_waits: int
    start: int
    frames: typing.Annotated[int, annotated_types.Gt(0)]
    window: typing.Annotated[float, annotated_types.Ge(0.0)]
    semaphores: dict[typing.Hashable, AIMDSemaphore]


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContext[** Params, Return](Context[Params, Return], _base.AsyncContext[Params, Return]):
    lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)
    semaphores: dict[typing.Hashable, AsyncAIMDSemaphore] = dataclasses.field(default_factory=dict)

    async def __aenter__(self):
        await self.semaphores.setdefault(
            self.keygen(*self.args, **self.kwargs),
            AsyncAIMDSemaphore(
                max_holds=self.max_holds,
                max_panes=self.max_panes,
                max_units=self.max_units,
                max_waits=self.max_waits,
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
class MultiContext[** Params, Return](Context[Params, Return], _base.MultiContext[Params, Return]):
    lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    semaphores: dict[typing.Hashable, MultiAIMDSemaphore] = dataclasses.field(default_factory=dict)

    def __enter__(self):
        self.semaphores.setdefault(
            self.keygen(*self.args, **self.kwargs),
            MultiAIMDSemaphore(
                max_holds=self.max_holds,
                max_panes=self.max_panes,
                max_units=self.max_units,
                max_waits=self.max_waits,
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
    frames: typing.Annotated[int, annotated_types.Gt(0)] = 1
    # TODO: make a sync and async version of the key return.
    keygen: typing.Callable[Params, typing.Hashable] = lambda *args, **kwargs: None

    # How many callees are allowed through concurrently before additional callees become waiters.
    max_holds: typing.Annotated[int, annotated_types.Gt(0)] = sys.maxsize

    max_panes: typing.Annotated[int, annotated_types.Gt(0)] = 1
    max_units: typing.Annotated[int, annotated_types.Gt(0)] = sys.maxsize

    # How many callees are allowed through or to wait concurrently before additional callees are rejected.
    max_waits: typing.Annotated[int, annotated_types.Gt(0)] = sys.maxsize

    # How many concurrent tokens to initialize with. This will never exceed given `soft` or `hard` values. Scaling
    #  follows AIMD control-flow rules. if this value is 1 and calls continue to fail, acquiring a token will incur an
    #  exponentially-increasing wait starting at 1 second before allowing the context to move forward.
    start: typing.Annotated[int, annotated_types.Gt(0)] = 1
    window: typing.Annotated[float, annotated_types.Ge(0.0)] = 0.0

    Exception: typing.ClassVar = Exception

    @typing.overload
    def __call__(
        self, decoratee: _base.AsyncDecoratee[Params, Return], /
    ) -> _base.AsyncDecorated[Params, Return]: ...

    @typing.overload
    def __call__(
        self, decoratee: _base.MultiDecoratee[Params, Return], /
    ) -> _base.MultiDecorated[Params, Return]: ...

    def __call__(
        self, decoratee: _base.Decoratee[Params, Return]
    ) -> _base.Decorated[Params, Return]:
        if not isinstance(decoratee, _base.Decorated):
            decoratee = _base.Decorator[Params, Return]()(decoratee)

        if inspect.iscoroutinefunction(decoratee):
            context = AsyncContext(signature=inspect.signature(decoratee), **dataclasses.asdict(self))
        else:
            context = MultiContext(signature=inspect.signature(decoratee), **dataclasses.asdict(self))

        decoratee.contexts = tuple([context, *decoratee.contexts])

        decorated = decoratee

        return decorated
