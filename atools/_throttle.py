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
    value: typing.Annotated[int, annotated_types.Ge(1)]
    history: History | None = dataclasses.field(init=False)
    penalty: Penalty | None = None

    window_end: EndFrame = 0.0
    window: Window | None = None

    n_holder: typing.Annotated[int, annotated_types.Ge(0)] = 0
    n_waiter: typing.Annotated[int, annotated_types.Ge(0)] = 0
    n_window: typing.Annotated[int, annotated_types.Ge(0)] = sys.maxsize

    # Hard maximums. Dynamic `value` will never exceed hard maximum.
    MAX_HOLDER: typing.Annotated[int, annotated_types.Ge(1)]
    MAX_WAITER: typing.Annotated[int, annotated_types.Ge(0)]
    MAX_WINDOW: typing.Annotated[int, annotated_types.Ge(1)]

    # TODO: Perhaps change this to a statically-sized list of _buckets_ or just a counter for start times in the last
    #  window. Growing and shrinking a heap will cause non-trivial overhead.
    condition: asyncio.Condition | threading.Condition

    @contextlib.contextmanager
    def _acquire(self) -> typing.Generator[typing.Callable[[], typing.Awaitable[None] | None], None, None]:
        # Having max_holders/holders be a part of this check looks odd, but it averts a race condition where a lot of
        #  waiters have built up and would have immediately become holders if just given a moment. i.e., we only want to
        #  count waiters that are blocked waiting.
        if self.MAX_HOLDER + self.MAX_WAITER <= self.n_holder + self.n_waiter:
            raise Exception(f'Throttle max waiter limit {self.MAX_WAITER} exceeded.')

        # FIXME this doesn't take care of the nth+1 through the window, the one that should take care of resetting the
        #  window after sleeping.
        match (
            (self.n_holder < self.value),
            (
                None if self.window is None
                else False if self.n_window < self.MAX_WINDOW
                else time.time()
            )
        ):
            case False, None:
                yield None
                self.n_holder += 1
            case False, False:
                self.n_holder += 1
                self.n_window += 1
                yield None
            case False, float(now) if self.window_end <= now:
                self.condition.notify(min(self.n_window, max(0, self.n_waiter)))
                self.window_end = now + self.window
                self.n_window = 1
                yield None
            case False, float(now) if now < self.window_end:
                self.n_waiter += 1
                yield lambda: self.condition.wait_for(
                    lambda: self.n_holder < self.value and self.n_window < self.MAX_WINDOW
                )
                self.n_waiter -= 1
            case True, None:
                self.n_waiter += 1
                yield lambda: self.condition.wait_for(lambda: self.n_holder < self.value)
                self.n_waiter -= 1
            case True, False:
                self.n_waiter += 1
                yield lambda: self.condition.wait_for(
                    lambda: self.n_holder < self.value and self.n_window < self.MAX_WINDOW
                )
                self.n_waiter -= 1
            case True, float(now) if self.window_end <= now:
                self.window_end = now + self.window
                self.n_window = 1
                yield None
            case True, float(now) if now < self.window_end:
                self.n_waiter += 1
                yield lambda: self.condition.wait_for(
                    lambda: self.n_holder < self.value and self.n_window < self.MAX_WINDOW
                )
                self.n_waiter -= 1
                self.n_window += 1

        self.n_holder += 1

    def _release(self, ok: bool) -> None:
        self.n_holder -= 1
        self.condition.notify(1)

        match ok:
            case False if self.value == 1:
                self.penalty = 1.0 if self.penalty is None else self.penalty * 2
            case False if self.value <= self.n_holder * 2:
                self.value //= 2

            case True if self.value == 1:
                self.value = 2 if self.penalty is None and self.value < self.MAX_HOLDER else 1
                self.penalty = None
            case True if self.value < self.n_holder * 2 and self.value < self.MAX_HOLDER:
                self.value += 1

        if 0 < (available := self.value - self.n_holder):
            self.condition.notify(available)

    @abc.abstractmethod
    def pause(self, penalty: Penalty) -> typing.Awaitable[None] | None: ...


@dataclasses.dataclass(kw_only=True)
class AsyncAIMDSemaphore(AIMDSemaphore):
    condition: asyncio.Condition = dataclasses.field(default_factory=asyncio.Condition)

    async def pause(self, penalty: Penalty) -> None:
        await asyncio.sleep(penalty)

    async def acquire(self) -> None:
        async with self.condition:
            with self._acquire() as call:
                if call is not None:
                    await call()

    async def release(self, ok: bool) -> None:
        async with self.condition:
            self._release(ok)


@dataclasses.dataclass(kw_only=True)
class MultiAIMDSemaphore(AIMDSemaphore):
    condition: threading.Condition = dataclasses.field(default_factory=threading.Condition)

    def pause(self, penalty: Penalty) -> None:
        time.sleep(penalty)

    def acquire(self) -> None:
        with self.condition:
            with self._acquire() as call:
                if call is not None:
                    call()

    def release(self, ok: bool) -> None:
        with self.condition:
            self._release(ok)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](_contexts.Context, abc.ABC):
    lock: dataclasses.Field[Lock]
    max_holder: typing.Annotated[int, annotated_types.Gt(0)]
    max_waiter: typing.Annotated[int, annotated_types.Gt(0)]
    max_window: typing.Annotated[int, annotated_types.Gt(0)]
    start: typing.Annotated[int, annotated_types.Gt(0)]
    semaphores: dict[typing.Hashable, AIMDSemaphore] = dataclasses.field(default_factory=dict)
    window: Window | None


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContext[** Params, Return](Context[Params, Return], _contexts.AsyncContext[Params, Return]):
    lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)
    semaphores: dict[typing.Hashable, AsyncAIMDSemaphore] = dataclasses.field(default_factory=dict)

    async def __aenter__(self):
        await self.semaphores.setdefault(
            self.key,
            AsyncAIMDSemaphore(
                value=self.start,
                MAX_HOLDER=self.max_holder,
                MAX_WAITER=self.max_waiter,
                MAX_WINDOW=self.max_window,
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
        match exc_type, exc_val, exc_tb:
            case None, None, None:
                await self.semaphores[self.key].release(ok=True)
            case _:
                await self.semaphores[self.key].release(ok=False)


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiContext[** Params, Return](Context[Params, Return], _contexts.MultiContext[Params, Return]):
    lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)
    semaphores: dict[typing.Hashable, MultiAIMDSemaphore] = dataclasses.field(default_factory=dict)

    def __enter__(self):
        self.semaphores.setdefault(
            self.key,
            MultiAIMDSemaphore(
                value=self.start,
                MAX_HOLDER=self.max_holder,
                MAX_WAITER=self.max_waiter,
                MAX_WINDOW=self.max_window,
                window=self.window,
            )
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
    keygen: typing.Callable[Params, typing.Hashable] = lambda *args, **kwargs: None
    # How many callees are allowed through concurrently before additional callees become waiters.
    max_holder: typing.Annotated[int, annotated_types.Gt(0)] = sys.maxsize
    # How many callees are allowed through or to wait concurrently before additional callees are rejected.
    max_waiter: typing.Annotated[int, annotated_types.Gt(0)] = sys.maxsize
    max_window: typing.Annotated[int, annotated_types.Gt(0)] = sys.maxsize
    start: typing.Annotated[int, annotated_types.Gt(0)] = 1
    # How many concurrent tokens to initialize with. This will never exceed given `soft` or `hard` values. Scaling
    #  follows AIMD control-flow rules. if this value is 1 and calls continue to fail, acquiring a token will incur an
    #  exponentially-increasing wait starting at 1 second before allowing the context to move forward.
    window: Window | None = None

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
                max_holder=self.max_holder,
                max_waiter=self.max_waiter,
                max_window=self.max_window,
                signature=inspect.signature(decoratee),
                start=self.start,
                window=self.window,
            )
        else:
            context = MultiContext(
                max_holder=self.max_holder,
                max_waiter=self.max_waiter,
                max_window=self.max_window,
                signature=inspect.signature(decoratee),
                start=self.start,
                window=self.window,
            )

        decoratee.contexts = tuple([context, *decoratee.contexts])

        decorated = decoratee

        return decorated
