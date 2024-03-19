from __future__ import annotations

import abc
import annotated_types
import asyncio
import collections
import concurrent.futures
import dataclasses
import inspect
import sys
import time
import threading
import types
import typing
import weakref

from . import _base


type Expire = float
type Key = typing.Hashable
type Keygen[** Params] = typing.Callable[Params, Key]


@dataclasses.dataclass(frozen=True, kw_only=True)
class Memo(abc.ABC):
    expire: Expire | None


@dataclasses.dataclass(frozen=True, kw_only=True)
class Pending[Return](Memo, abc.ABC):
    future: asyncio.Future[Return] | concurrent.futures.Future[Return]


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncPending[Return](Pending[Return]):
    future: asyncio.Future[Return] = dataclasses.field(default_factory=asyncio.Future)


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiPending[Return](Pending):
    future: concurrent.futures.Future[Return] = dataclasses.field(default_factory=concurrent.futures.Future)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Raised(Memo):
    e: BaseException


@dataclasses.dataclass(frozen=True, kw_only=True)
class Returned[Return](Memo, Exception):
    value: Return


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](_base.Context[Params, Return], abc.ABC):
    args: Params.args
    kwargs: Params.kwargs
    pending: Pending
    signature: inspect.Signature


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContext[** Params, Return](Context[Params, Return], _base.AsyncContext[Params, Return]):
    lock: asyncio.Lock = dataclasses.field(default_factory=lambda: asyncio.Lock())

    async def __call__(self, return_: Return) -> None:
        self.pending.future.set_result(return_)

    @typing.overload
    async def __aexit__[ExcType: type[BaseException]](
        self, exc_type: type[ExcType], exc_val: ExcType, exc_tb: types.TracebackType
    ) -> object: ...

    @typing.overload
    async def __aexit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None: ...

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if (exc_type, exc_val, exc_tb) == (None, None, None):
            return None

        self.pending.future.set_exception(exc_val)


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiContext[** Params, Return](Context[Params, Return], _base.MultiContext[Params, Return]):
    lock: threading.Lock = dataclasses.field(default_factory=lambda: threading.Lock())

    def __call__(self, return_: Return) -> None:
        self.pending.future.set_result(return_)

    @typing.overload
    def __exit__[ExcType: type[BaseException]](
        self, exc_type: type[ExcType], exc_val: ExcType, exc_tb: types.TracebackType
    ) -> object: ...

    @typing.overload
    def __exit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None: ...

    def __exit__(self, exc_type, exc_val, exc_tb):
        if (exc_type, exc_val, exc_tb) == (None, None, None):
            return None

        self.pending.future.set_exception(exc_val)


@dataclasses.dataclass(frozen=True, kw_only=True)
class CreateContext[** Params, Return](_base.CreateContext[Params, Return], abc.ABC):
    duration: typing.Annotated[float, annotated_types.Ge(0.0)] | None
    keygen: Keygen[Params]
    lock: dataclasses.Field[threading.Lock] = dataclasses.field(default_factory=threading.Lock)
    memo_by_key: collections.OrderedDict[typing.Hashable, Memo] = dataclasses.field(
        default_factory=collections.OrderedDict
    )
    memo_by_key_by_instance: weakref.WeakKeyDictionary[
        _base.Instance, dict[typing.Hashable, Memo]
    ] = dataclasses.field(default_factory=weakref.WeakKeyDictionary)
    signature: inspect.signature
    size: int

    BoundCreateContext: typing.ClassVar[type[BoundCreateContext]]
    Context: typing.ClassVar[type[Context]] = Context
    Pending: typing.ClassVar[type[Pending]] = Pending

    def __call__(
        self: AsyncCreateContext[Params, Return] | MultiCreateContext[Params, Return],
        args: Params.args,
        kwargs: Params.kwargs,
    ) -> (
        AsyncContext[Params, Return]
        | MultiContext[Params, Return]
        | _base.HerdFollower[Return]
        | _base.ShortCircuit[Return]
    ):
        key = self.keygen(*args, **kwargs)
        match self.memo_by_key.get(key):
            case Returned(expire=expire, value=value) if expire is None or time.time() < expire:
                self.memo_by_key.move_to_end(key)
                return _base.ShortCircuit[Return](value=value)
            case Raised(e=e, expire=expire) if expire is None or time.time() < expire:
                self.memo_by_key.move_to_end(key)
                raise e
            case Pending(expire=expire, future=future) if expire is None or time.time() < expire:
                self.memo_by_key.move_to_end(key)
                if not future.done():
                    return _base.HerdFollower(future=future)
                else:
                    try:
                        self.memo_by_key[key] = Returned(expire=expire, value=(value := future.result()))
                        return _base.ShortCircuit[Return](value=value)
                    except Exception as e:
                        self.memo_by_key[key] = Raised(expire=expire, e=e)
                        raise
            case None | Pending() | Raised() | Returned():
                pending = self.memo_by_key[key] = self.Pending(
                    expire=None if self.duration is None else time.time() + self.duration
                )
                self.memo_by_key.move_to_end(key)
                if self.size is not None and self.size < len(self.memo_by_key):
                    self.memo_by_key.popitem(last=False)
                return self.Context(
                    args=args,
                    kwargs=kwargs,
                    pending=pending,
                    signature=self.signature,
                )

    def __get__(self, instance: _base.Instance, owner) -> BoundCreateContext[Params, Return]:
        with self.lock:
            return self.BoundCreateContext[Params, Return](
                duration=self.duration,
                instance=instance,
                keygen=self.keygen,
                memo_by_key=self.memo_by_key_by_instance.setdefault(instance, collections.OrderedDict()),
                memo_by_key_by_instance=self.memo_by_key_by_instance,
                signature=self.signature,
                size=self.size,
            )


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncCreateContext[** Params, Return](CreateContext[Params, Return], _base.AsyncCreateContext[Params, Return]):
    BoundCreateContext: typing.ClassVar[type[AsyncBoundCreateContext]]
    Context: typing.ClassVar[type[AsyncContext]] = AsyncContext
    Pending: typing.ClassVar[type[AsyncPending]] = AsyncPending


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiCreateContext[** Params, Return](CreateContext[Params, Return], _base.MultiCreateContext[Params, Return]):
    BoundCreateContext: typing.ClassVar[type[MultiBoundCreateContext]]
    Context: typing.ClassVar[type[MultiContext]] = MultiContext
    Pending: typing.ClassVar[type[MultiPending]] = MultiPending


@dataclasses.dataclass(frozen=True, kw_only=True)
class BoundCreateContext[** Params, Return](
    CreateContext[Params, Return], _base.BoundCreateContext[Params, Return], abc.ABC
):
    ...


CreateContext.BoundCreateContext = BoundCreateContext


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncBoundCreateContext[** Params, Return](
    BoundCreateContext[Params, Return],
    AsyncCreateContext[Params, Return],
    _base.AsyncBoundCreateContext[Params, Return],
    abc.ABC,
):
    ...


AsyncCreateContext.BoundCreateContext = AsyncBoundCreateContext


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiBoundCreateContext[** Params, Return](
    BoundCreateContext[Params, Return],
    MultiCreateContext[Params, Return],
    _base.MultiBoundCreateContext[Params, Return],
    abc.ABC
):
    ...


MultiCreateContext.BoundCreateContext = MultiBoundCreateContext


@dataclasses.dataclass(frozen=True)
class Decorator[** Params, Return]:
    name: _base.Name = ...
    _: dataclasses.KW_ONLY = ...
    duration: typing.Annotated[float, annotated_types.Ge(0.0)] | None = None
    keygen: Keygen[Params] = ...
    size: int = sys.maxsize

    @typing.overload
    def __call__(
        self, decoratee: _base.AsyncDecoratee[Params, Return], /
    ) -> _base.AsyncDecorated[Params, Return]: ...

    @typing.overload
    def __call__(
        self, decoratee: _base.MultiDecoratee[Params, Return], /
    ) -> _base.MultiDecorated[Params, Return]: ...

    def __call__(self, decoratee, /):
        if not isinstance(decoratee, _base.Decorated):
            decoratee = _base.Decorator[Params, Return](name=self.name)(decoratee)

        signature = inspect.signature(decoratee.decoratee)
        if (keygen := self.keygen) is ...:
            def keygen(*args, **kwargs) -> typing.Hashable:
                bind = signature.bind(*args, **kwargs)
                bind.apply_defaults()

                return bind.args, tuple(sorted(bind.kwargs))

        if inspect.iscoroutinefunction(decoratee.decoratee):
            decoratee: _base.AsyncDecorated[Params, Return]
            decorated: _base.AsyncDecorated[Params, Return] = _base.AsyncDecorated[Params, Return](
                create_contexts=tuple([
                    AsyncCreateContext(
                        duration=self.duration,
                        keygen=keygen,
                        signature=signature,
                        size=self.size,
                    ),
                    *decoratee.create_contexts,
                ]),
                decoratee=decoratee.decoratee,
                register=decoratee.register,
                register_key=decoratee.register_key,
                __name__=decoratee.__name__,
                __qualname__=decoratee.__qualname__,
            )
        else:
            decoratee: _base.MultiDecorated[Params, Return]
            decorated: _base.MultiDecorated[Params, Return] = _base.MultiDecorated[Params, Return](
                create_contexts=tuple([
                    MultiCreateContext(
                        duration=self.duration,
                        keygen=keygen,
                        signature=signature,
                        size=self.size,
                    ),
                    *decoratee.create_contexts,
                ]),
                decoratee=decoratee.decoratee,
                register=decoratee.register,
                register_key=decoratee.register_key,
                __name__=decoratee.__name__,
                __qualname__=decoratee.__qualname__,
            )

        decorated.register.decoratees[decorated.register_key] = decorated

        return decorated
