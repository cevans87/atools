from __future__ import annotations

import abc
import annotated_types
import asyncio
import collections
import concurrent.futures
import dataclasses
import hashlib
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
import sqlalchemy.orm
import sqlalchemy.ext.asyncio

from . import _base


type Duration = float
type Expire = float
type Key = str
type Keygen[** Params] = typing.Callable[Params, Key]
type Value = object

type Bytes = bytes


@typing.runtime_checkable
class Serializer[Return](typing.Protocol):
    def dumps(self, return_: Return) -> Bytes:
        ...

    def loads(self, bytes_: Bytes) -> Return:
        ...


class Base(sqlalchemy.orm.DeclarativeBase):
    ...


class MemoBase(Base):
    expire: sqlalchemy.orm.Mapped[Expire | None] = sqlalchemy.orm.mapped_column()
    key: sqlalchemy.orm.Mapped[str] = sqlalchemy.orm.mapped_column(primary_key=True, unique=True)
    value: sqlalchemy.orm.Mapped[bytes] = sqlalchemy.orm.mapped_column()


#@dataclasses.dataclass(frozen=True, kw_only=True)
#class Pending[Return](Memo, abc.ABC):
#    future: asyncio.Future[Return] | concurrent.futures.Future[Return]


#@dataclasses.dataclass(frozen=True, kw_only=True)
#class Cache[Key, Return]:
#    duration: Duration
#    engine: sqlalchemy.Engine = dataclasses.field(init=True)
#    size: int
#
#    def __len__(self) -> int:
#        ...
#
#    def get(self, key: Key) -> Return | Memo[Return]:
#        with sqlalchemy.orm.Session(self.engine) as session:
#            session.begin()
#
#    def set(self, key: Key, memo: Memo) -> None:
#        ...



#@dataclasses.dataclass(frozen=True, kw_only=True)
#class Memo(abc.ABC):
#    expire: Expire | None


#@dataclasses.dataclass(frozen=True, kw_only=True)
#class Pending[Return](Memo, abc.ABC):
#    future: asyncio.Future[Return] | concurrent.futures.Future[Return]
#
#
#@dataclasses.dataclass(frozen=True, kw_only=True)
#class AsyncPending[Return](Pending[Return]):
#    session: sqlalchemy.ext.asyncio.AsyncSession
#
#
#@dataclasses.dataclass(frozen=True, kw_only=True)
#class MultiPending[Return](Pending):
#    session: sqlalchemy.orm.Session


@dataclasses.dataclass(frozen=True, kw_only=True)
class Returned[Return](Memo, Exception):
    value: Return


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](_base.Context[Params, Return], abc.ABC):
    #args: Params.args
    #kwargs: Params.kwargs
    memo: MemoBase
    session: sqlalchemy.ext.asyncio.AsyncSession | sqlalchemy.orm.Session
    #signature: inspect.Signature


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContext[** Params, Return](Context[Params, Return], _base.AsyncContext[Params, Return]):
    session: sqlalchemy.ext.asyncio.AsyncSession

    async def __call__(self, return_: Return) -> None:
        self.memo.value = return_
        self.session.add(self.memo)

    async def __aenter__(self) -> typing.Self:
        # TODO lock the row
        await self.session.begin()
        return self

    @typing.overload
    async def __aexit__[ExcType: type[BaseException]](
        self, exc_type: type[ExcType], exc_val: ExcType, exc_tb: types.TracebackType
    ) -> object: ...

    @typing.overload
    async def __aexit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None: ...

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if (exc_type, exc_val, exc_tb) == (None, None, None):
            await self.session.rollback()
        else:
            await self.session.commit()


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiContext[** Params, Return](Context[Params, Return], _base.MultiContext[Params, Return]):
    session: sqlalchemy.orm.Session

    def __call__(self, return_: Return) -> None:
        self.memo.value = return_
        self.session.add(self.memo)

    def __enter__(self) -> typing.Self:
        self.session.begin()
        return self

    @typing.overload
    def __exit__[ExcType: type[BaseException]](
        self, exc_type: type[ExcType], exc_val: ExcType, exc_tb: types.TracebackType
    ) -> object: ...

    @typing.overload
    def __exit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None: ...

    def __exit__(self, exc_type, exc_val, exc_tb):
        if (exc_type, exc_val, exc_tb) == (None, None, None):
            self.session.commit()
        else:
            self.session.rollback()


@dataclasses.dataclass(frozen=True, kw_only=True)
class CreateContext[** Params, Return](_base.CreateContext[Params, Return], abc.ABC):
    duration: typing.Annotated[float, annotated_types.Ge(0.0)] | None
    engine: sqlalchemy.ext.asyncio.AsyncEngine | sqlalchemy.Engine
    keygen: Keygen[Params]
    lock: dataclasses.Field[threading.Lock] = dataclasses.field(default_factory=threading.Lock)
    #memo_by_key: dict[Key, MemoBase]
    #memo_by_key_by_instance: weakref.WeakKeyDictionary[_base.Instance, dict[Key, MemoBase]] = dataclasses.field(
    #    default_factory=weakref.WeakKeyDictionary
    #)
    memo_t: type[MemoBase]
    serializer: Serializer
    signature: inspect.signature
    size: int

    BoundCreateContext: typing.ClassVar[type[BoundCreateContext]]
    Context: typing.ClassVar[type[Context]] = Context

    @typing.overload
    async def __call__(
        self: AsyncCreateContext[Params, Return],
        args: Params.args,
        kwargs: Params.kwargs,
    ) -> AsyncContext[Params, Return] | Return: ...

    @typing.overload
    def __call__(
        self: MultiCreateContext[Params, Return],
        args: Params.args,
        kwargs: Params.kwargs,
    ) -> MultiContext[Params, Return] | Return: ...

    def __call__(self, args, kwargs): ...
    del __call__

    def __get__(self, instance: _base.Instance, owner) -> BoundCreateContext[Params, Return]:
        with self.lock:
            return self.BoundCreateContext[Params, Return](
                duration=self.duration,
                engine=self.engine,
                keygen=self.keygen,
                memo_t=type('Memo', (MemoBase,), {'__tablename__': f'{self.memo_t.__tablename__}.{instance}'}),
                signature=self.signature,
                size=self.size,
            )


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncCreateContext[** Params, Return](CreateContext[Params, Return], _base.AsyncCreateContext[Params, Return]):
    engine: sqlalchemy.ext.asyncio.AsyncEngine

    BoundCreateContext: typing.ClassVar[type[AsyncBoundCreateContext]]
    Context: typing.ClassVar[type[AsyncContext]] = AsyncContext

    async def __call__(
        self: AsyncCreateContext[Params, Return] | MultiCreateContext[Params, Return],
        args: Params.args,
        kwargs: Params.kwargs,
    ) -> AsyncContext[Params, Return] | MultiContext[Params, Return] | Return:
        key = self.keygen(*args, **kwargs)

        async with sqlalchemy.ext.asyncio.AsyncSession(self.engine) as session, session.begin():
            match (
                await session.execute(sqlalchemy.select(self.memo_t).with_for_update().where(key=key))
            ).first():
                case self.memo_t(memo) if memo.value is None or (
                    memo.expire is not None and memo.expire <= time.time()
                ):
                    ...
                case self.memo_t(memo) if memo.expire is None or time.time() <= memo.expire:
                    return self.serializer.loads(memo.value)
                case _:
                    ...

        return self.Context(
            memo=self.memo_t(key=self.key),
            session=session,
        )

        print(result.fetchall())


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiCreateContext[** Params, Return](CreateContext[Params, Return], _base.MultiCreateContext[Params, Return]):
    engine: sqlalchemy.Engine
    memo_t: type[MemoBase]

    BoundCreateContext: typing.ClassVar[type[MultiBoundCreateContext]]
    Context: typing.ClassVar[type[MultiContext]] = MultiContext


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

        class Memo(MemoBase):
            __tablename__ = self.name

        if inspect.iscoroutinefunction(decoratee.decoratee):
            decoratee: _base.AsyncDecorated[Params, Return]
            decorated: _base.AsyncDecorated[Params, Return] = dataclasses.replace(
                decoratee,
                create_contexts=tuple([
                    AsyncCreateContext(
                        duration=self.duration,
                        keygen=keygen,
                        memo_t=Memo,
                        serializer=self.serializer,
                        signature=signature,
                        size=self.size,
                        table_name=self.name,
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
                        memo_t=Memo,
                        serializer=self.serializer,
                        signature=signature,
                        size=self.size,
                        table_name=self.name,
                    ),
                    *decoratee.create_contexts,
                ]),
            )

        decorated.register.decoratees[decorated.register_key] = decorated

        return decorated
