from __future__ import annotations

import abc
import annotated_types
import asyncio
import collections
import concurrent.futures
import dataclasses
import inspect
import json
import sys
import time
import threading
import types
import typing
import weakref

import pydantic
import sqlalchemy
import sqlmodel

from . import _base


type Duration = float
type Expire = float
type Key = typing.Hashable
type Keygen[** Params] = typing.Callable[Params, Key]

type Bytes = bytes


class Row(sqlmodel.SQLModel):
    key: Key = sqlmodel.Field(primary_key=True)
    bytes_: Bytes

    def of(self, key: Key) -> Row:
        return Memo[Return]()


@typing.runtime_checkable
class Serializer[Return](typing.Protocol):
    def dumps(self, return_: Return) -> Bytes:
        ...

    def loads(self, bytes_: Bytes) -> Return:
        ...


class Memo(abc.ABC):

    def of(self, key: Key, session: sqlmodel.Session) -> Memo:
        row = session.exec(sqlmodel.select(Row).where(Row.key == key)).first()
        if ...:
            return Pending
        elif ...:
            Return

        return Memo[Return]()


@dataclasses.dataclass(frozen=True, kw_only=True)
class Cache[Key, Return]:
    duration: Duration
    engine: sqlalchemy.Engine = dataclasses.field(init=True)
    size: int

    def __len__(self) -> int:
        ...

    @classmethod
    def of(
        cls,
        key: Key,
        database: str,
        duration: Duration,
        host: str,
        password: str,
        size: pydantic.PositiveInt,
        table_name: str,
        username: str,
    ) -> Cache:
        return cls(
            duration=duration,
            engine=sqlalchemy.create_engine(
                sqlalchemy.URL.create(
                    drivername='sqlite',
                    database=database,
                    host=host,
                    password=password,
                    username=username,
                )
            ),
        )

    def get(self, key: Key) -> Memo[Return]:
        with sqlmodel.Session(self.engine) as session:
            return session.exec(sqlmodel.select(Memo[Return]).where(Memo[Return].key == key)).first()

    def set(self, key: Key, memo: Memo) -> None:
        ...



#@dataclasses.dataclass(frozen=True, kw_only=True)
#class Memo(abc.ABC):
#    expire: Expire | None


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
    # TODO: Implement expiration
    # key_by_expire: dict[Expire, Key] = dataclasses.field(default_factory=dict)
    memo_by_key: dict[Key, Memo]
    memo_by_key_by_instance: weakref.WeakKeyDictionary[_base.Instance, dict[Key, Memo]] = dataclasses.field(
        default_factory=weakref.WeakKeyDictionary
    )
    serializer: Serializer
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
        match self.cache.get(key):
            case Returned(expire=expire, value=value) if expire is None or time.time() < expire:
                self.cache.move_to_end(key)
                return _base.ShortCircuit[Return](value=value)
            case Raised(e=e, expire=expire) if expire is None or time.time() < expire:
                self.cache.move_to_end(key)
                raise e
            case Pending(expire=expire, future=future) if expire is None or time.time() < expire:
                self.cache.move_to_end(key)
                if not future.done():
                    return _base.HerdFollower(future=future)
                else:
                    try:
                        self.cache[key] = Returned(expire=expire, value=(value := future.result()))
                        return _base.ShortCircuit[Return](value=value)
                    except Exception as e:
                        self.cache[key] = Raised(expire=expire, e=e)
                        raise
            case None | Pending() | Raised() | Returned():
                pending = self.cache[key] = self.Pending(
                    expire=None if self.duration is None else time.time() + self.duration
                )
                self.cache.move_to_end(key)
                if self.size is not None and self.size < len(self.cache):
                    self.cache.popitem(last=False)
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
                cache=self.cache_by_instance.setdefault(instance, dataclasses.replace(
                    self.cache,
                    table_name=self.cache.table_name,
                )),
                cache_by_instance=self.cache_by_instance,
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
    serializer: Serializer = ...
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
            def keygen(*args, **kwargs) -> Key:
                bind = signature.bind(*args, **kwargs)
                bind.apply_defaults()

                return bind.args, tuple(sorted(bind.kwargs))

        if inspect.iscoroutinefunction(decoratee.decoratee):
            decoratee: _base.AsyncDecorated[Params, Return]
            decorated: _base.AsyncDecorated[Params, Return] = dataclasses.replace(
                decoratee,
                create_contexts=tuple([
                    AsyncCreateContext(
                        duration=self.duration,
                        keygen=keygen,
                        serializer=self.serializer,
                        signature=signature,
                        size=self.size,
                    ),
                    *decoratee.create_contexts,
                ]),
            )
        else:
            decoratee: _base.MultiDecorated[Params, Return]
            decorated: _base.MultiDecorated[Params, Return] = dataclasses.replace(
                decoratee,
                create_contexts=tuple([
                    MultiCreateContext(
                        duration=self.duration,
                        keygen=keygen,
                        serializer=self.serializer,
                        signature=signature,
                        size=self.size,
                    ),
                    *decoratee.create_contexts,
                ]),
            )

        decorated.register.decoratees[decorated.register_key] = decorated

        return decorated
