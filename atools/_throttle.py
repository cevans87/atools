import abc
import collections
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
    """Semaphore with AIMD behavior.

    Definitions:
        - holders - Callers that have acquired a semaphore value but have not released are holders.
        - herders - Holders that are allowed to begin execution within the current temporal `frame` are herders.
        - waiters - Callers that are blocked either on the herd or hold limit are waiters.

        - frame - Discreet temporal checkpoints after which another `max_herders` herders are allowed through.
        - `window` - The amount of time that must pass after an individual frame expires before it is replenished.

    'value' behavior:
        - No more than the current `value` callers are approved to `hold`.
        - Value increases by 1 if a holder releases without raising an exception and the number of holders is greater
          than half of value.

    'checkpoint' behavior:
        -

    Value
    """
    max_herd: int
    max_hold: int
    max_wait: int

    value: int

    frames: collections.deque[typing.Annotated[float, annotated_types.Ge(0.0)]]
    window: typing.Annotated[float, annotated_types.Ge(0.0)]

    n_herd: int = ...
    n_hold: int = 0
    n_wait: int = 0

    sleeper = False

    herd_condition: asyncio.Condition | threading.Condition
    hold_condition: asyncio.Condition | threading.Condition

    def __post_init__(self) -> None:
        self.n_herd = self.max_herd

    def _acquire_hold(self) -> typing.Generator[typing.Callable[[], typing.Awaitable[None] | None], None, None]:
        while self.n_hold >= max(1, self.value):
            yield from self._wait_for(self.hold_condition, lambda: self.n_hold < max(1, self.value))
        self.n_hold += 1

        if self.value <= 0:
            yield lambda: self._sleep(self.hold_condition, 2.0 ** -self.value)

    def _acquire_herd(self) -> typing.Generator[typing.Callable[[], typing.Awaitable[None] | None], None, None]:
        while self.n_herd >= self.max_herd:
            if self.sleeper:
                yield from self._wait_for(self.herd_condition, lambda: self.n_herd < self.max_herd)
            else:
                if (now := time.time()) < self.frames[0]:
                    self.sleeper = True
                    yield lambda: self._sleep(self.herd_condition, self.frames[0] - now)
                    self.sleeper = False
                self.frames.popleft()
                self.frames.append(now + self.window)
                self.n_herd = 0
                self.herd_condition.notify(self.max_herd + 1)
        self.n_herd += 1

    def _release(self, ok: bool) -> None:
        match ok:
            case True if self.value <= 0:
                self.value = 1
            case True if self.n_hold in range((self.value // 2) + 1, self.max_hold):
                self.value += 1
                self.hold_condition.notify(1)
            case False if self.value > 0:
                self.value //= 2
            case False:
                self.value -= 1

        self.n_hold -= 1
        self.hold_condition.notify(1)

    @abc.abstractmethod
    def _sleep(self, condition: asyncio.Condition | threading.Condition, time_: Time) -> typing.Awaitable[None] | None:
        raise NotImplemented

    def _wait_for(
        self, condition: asyncio.Condition | threading.Condition, predicate: typing.Callable[[], bool]
    ) -> None:
        if self.n_wait >= self.max_wait:
            raise Exception(f'{self.max_wait=} exceeded.')

        self.n_wait += 1
        try:
            yield lambda: condition.wait_for(predicate=predicate)
        finally:
            self.n_wait -= 1


@dataclasses.dataclass(kw_only=True)
class AsyncAIMDSemaphore(AIMDSemaphore):
    herd_condition: asyncio.Condition = dataclasses.field(default_factory=lambda: asyncio.Condition())
    hold_condition: asyncio.Condition = dataclasses.field(default_factory=lambda: asyncio.Condition())

    async def _sleep(self, condition: asyncio.Condition, delay: float) -> None:
        condition.release()
        try:
            await asyncio.sleep(delay)
        finally:
            await condition.acquire()

    async def acquire(self) -> None:
        async with self.hold_condition:
            for call in self._acquire_hold():
                await call()
        async with self.herd_condition:
            for call in self._acquire_herd():
                await call()

    async def release(self, ok: bool) -> None:
        async with self.hold_condition:
            self._release(ok)


@dataclasses.dataclass(kw_only=True)
class MultiAIMDSemaphore(AIMDSemaphore):
    herd_condition: threading.Condition = dataclasses.field(default_factory=lambda: threading.Condition())
    hold_condition: threading.Condition = dataclasses.field(default_factory=lambda: threading.Condition())

    def _sleep(self, condition: threading.Condition, delay: float) -> None:
        condition.release()
        try:
            time.sleep(delay)
        finally:
            condition.acquire()

    def acquire(self) -> None:
        with self.hold_condition:
            for call in self._acquire_hold():
                call()
        with self.herd_condition:
            for call in self._acquire_herd():
                call()

    def release(self, ok: bool) -> None:
        with self.hold_condition:
            self._release(ok)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](_contexts.Context, abc.ABC):
    keygen: typing.Callable[Params, typing.Hashable]
    lock: dataclasses.Field[Lock]
    max_herd: int
    max_hold: int
    wait_hold: int
    start: int
    frames: typing.Annotated[int, annotated_types.Gt(0)]
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
                frames=collections.deque([float('-inf') for _ in range(self.frames)], maxlen=self.frames),
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
                frames=collections.deque([float('-inf') for _ in range(self.frames)], maxlen=self.frames),
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
    frames: typing.Annotated[int, annotated_types.Gt(0)] = 1
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
            context = AsyncContext(signature=inspect.signature(decoratee), **dataclasses.asdict(self))
        else:
            context = MultiContext(signature=inspect.signature(decoratee), **dataclasses.asdict(self))

        decoratee.contexts = tuple([context, *decoratee.contexts])

        decorated = decoratee

        return decorated
