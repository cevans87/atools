import abc
import annotated_types
import asyncio
import dataclasses
import functools
import inspect
import sys
import time
import threading
import types
import typing


from . import _base


type Keygen[** Params] = typing.Callable[Params, typing.Hashable]


@dataclasses.dataclass(frozen=True, kw_only=True)
class Memo(abc.ABC):
    ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class Pending(Memo, abc.ABC):
    event: asyncio.Event | threading.Event


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncPending(Pending):
    event: asyncio.Event = dataclasses.field(default_factory=asyncio.Event)


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiPending(Pending):
    event: threading.Event = dataclasses.field(default_factory=threading.Event)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Raised(Memo):
    e: BaseException
    expire: float | None


@dataclasses.dataclass(frozen=True, kw_only=True)
class Returned[Return](Memo, Exception):
    expire: float | None
    value: Return


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](_base.Context[Params, Return], abc.ABC):
    duration: typing.Annotated[float, annotated_types.Ge(0.0)] | None
    keygen: Keygen[Params]
    memos: dict[typing.Hashable, Memo] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContext[** Params, Return](Context[Params, Return], _base.AsyncContext[Params, Return]):
    lock: asyncio.Lock = dataclasses.field(default_factory=lambda: asyncio.Lock())

    async def __call__(self) -> _base.ShortCircuit[Return] | None:
        key = self.keygen(*self.args, **self.kwargs)
        async with self.lock:
            while True:
                match self.memos.get(key):
                    case Returned(expire=expire, value=value) if expire is None or time.time() < expire:
                        return _base.ShortCircuit[Return](value=value)
                    case Raised(e=e, expire=expire) if expire is None or time.time() < expire:
                        raise e
                    case Raised() | Returned() | None:
                        self.memos[key] = AsyncPending()
                    case AsyncPending(event=event) if self.return_ is ...:
                        self.lock.release()
                        await event.wait()
                        await self.lock.acquire()
                        continue
                    case AsyncPending(event=event):
                        self.memos[key] = Returned[Return](
                            expire=None if self.duration is None else time.time() + self.duration,
                            value=self.return_,
                        )
                        event.set()

                return None

    @typing.overload
    async def __aexit__[ExcType: type[BaseException]](
        self, exc_type: type[ExcType], exc_val: ExcType, exc_tb: types.TracebackType
    ) -> object: ...

    @typing.overload
    async def __aexit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None: ...

    async def __aexit__[ExcType: type[BaseException]](
        self, exc_type: type[ExcType] | None, exc_val: ExcType | None, exc_tb: types.TracebackType | None
    ) -> None:
        if (exc_type, exc_val, exc_tb) == (None, None, None):
            return None

        key = self.keygen(*self.args, **self.kwargs)
        async with self.lock:
            match self.memos.get(key):
                case AsyncPending(event=event):
                    self.memos[key] = Raised(
                        e=exc_val, expire=None if self.duration is None else time.time() + self.duration
                    )
                    event.set()


# TODO: we actually do need Decorated classes so that we can override the __get__ methods and create different memoize
#  lrus for each cls/self that passes through.


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiContext[** Params, Return](Context[Params, Return], _base.MultiContext[Params, Return]):
    lock: threading.Lock = dataclasses.field(default_factory=lambda: threading.Lock())

    def __call__(self) -> _base.ShortCircuit[Return] | None:
        key = self.keygen(*self.args, **self.kwargs)
        with self.lock:
            while True:
                match self.memos.get(key):
                    case Returned(expire=expire, value=value) if expire is None or time.time() < expire:
                        return _base.ShortCircuit[Return](value=value)
                    case Raised(e=e, expire=expire) if expire is None or time.time() < expire:
                        raise e
                    case Raised() | Returned() | None:
                        self.memos[key] = AsyncPending()
                    case MultiPending(event=event) if self.return_ is ...:
                        self.lock.release()
                        event.wait()
                        self.lock.acquire()
                        continue
                    case MultiPending(event=event):
                        self.memos[key] = Returned[Return](
                            expire=None if self.duration is None else time.time() + self.duration,
                            value=self.return_,
                        )
                        event.set()

                return None

    @typing.overload
    def __exit__[ExcType: type[BaseException]](
        self, exc_type: type[ExcType], exc_val: ExcType, exc_tb: types.TracebackType
    ) -> object: ...

    @typing.overload
    def __exit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None: ...

    def __exit__[ExcType: type[BaseException]](
        self, exc_type: type[ExcType] | None, exc_val: ExcType | None, exc_tb: types.TracebackType | None
    ) -> None:
        if (exc_type, exc_val, exc_tb) == (None, None, None):
            return None

        key = self.keygen(*self.args, **self.kwargs)
        with self.lock:
            match self.memos.get(key):
                case MultiPending(event=event):
                    self.memos[key] = Raised(
                        e=exc_val, expire=None if self.duration is None else time.time() + self.duration
                    )
                    event.set()


@dataclasses.dataclass(frozen=True)
class Decorator[** Params, Return]:
    name: _base.Name = ...
    _: dataclasses.KW_ONLY = ...
    duration: typing.Annotated[float, annotated_types.Ge(0.0)] | None = None
    keygen: Keygen[Params] = ...
    size: int = sys.maxsize

    @typing.overload
    def __call__[** Params, Return](
        self, decoratee: _base.AsyncDecoratee[Params, Return], /
    ) -> _base.AsyncDecorated[Params, Return]: ...

    @typing.overload
    def __call__[** Params, Return](
        self, decoratee: _base.MultiDecoratee[Params, Return], /
    ) -> _base.MultiDecorated[Params, Return]: ...

    def __call__[** Params, Return](
        self, decoratee: _base.Decoratee[Params, Return], /
    ) -> _base.Decorated[Params, Return]:
        if not isinstance(decoratee, _base.Decorated):
            decoratee = _base.Decorator[Params, Return](name=self.name)(decoratee)

        signature = inspect.signature(decoratee)
        if (keygen := self.keygen) is ...:
            def keygen(*args, **kwargs) -> typing.Hashable:
                bind = signature.bind(*args, **kwargs)
                bind.apply_defaults()

                return bind.args, tuple(sorted(bind.kwargs))

        if inspect.iscoroutinefunction(decoratee):
            decoratee: _base.AsyncDecorated[Params, Return]
            decorated: _base.AsyncDecorated[Params, Return] = dataclasses.replace(
                decoratee, contexts=tuple([
                    AsyncContext(
                        duration=self.duration,
                        keygen=keygen,
                        signature=inspect.signature(decoratee),
                    ),
                ])
            )
        else:
            decoratee: _base.MultiDecorated[Params, Return]
            decorated: _base.MultiDecorated[Params, Return] = dataclasses.replace(
                decoratee, contexts=tuple([
                    MultiContext(
                        duration=self.duration,
                        keygen=keygen,
                        signature=inspect.signature(decoratee),
                    ),
                    *decoratee.contexts
                ])
            )

        decorated = decorated.register.decoratees[decorated.key] = functools.wraps(decoratee, updated=())(decorated)

        return decorated
