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
import sqlalchemy.dialects.sqlite
import sqlalchemy.ext.asyncio
import sqlalchemy.orm

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


class RowBase(Base):
    expire: sqlalchemy.orm.Mapped[Expire | None] = sqlalchemy.orm.mapped_column()
    key: sqlalchemy.orm.Mapped[str] = sqlalchemy.orm.mapped_column(primary_key=True, unique=True)
    value: sqlalchemy.orm.Mapped[bytes] = sqlalchemy.orm.mapped_column()


class Session[Return](abc.ABC):

    def add(self, return_: Return) -> None:
        ...

    @typing.overload
    async def commit(self) -> None: ...
    @typing.overload
    def commit(self) -> None: ...
    def commit(self): ...
    del commit

    @typing.overload
    async def rollback(self: AsyncSession[Return]) -> None: ...
    @typing.overload
    def rollback(self: MultiSession[Return]) -> None: ...
    def rollback(self): ...
    del rollback


class AsyncSession[Return]:

    def add(self, return_: Return):
        ...

    async def commit(self):
        ...

    async def rollback(self):
        ...


class MultiSession[Return]:

    def add(self, return_: Return):
        ...

    def commit(self):
        ...

    def rollback(self):
        ...


#class Future[Return]:
#    ...
#
#
#class AsyncFuture[Return](Future[Return]):
#    ...
#
#
#class MultiFuture[Return](Future[Return]):
#    ...


#@dataclasses.dataclass(frozen=True, kw_only=True)
#class Cache[Key, Return]:
#    duration: Duration
#    engine: sqlalchemy.Engine = dataclasses.field(init=True)
#    size: int
#
#    def __len__(self) -> int:
#        ...
#
#    async def get(self, key: Key) -> Return | AsyncFuture[Return]:
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


#@dataclasses.dataclass(frozen=True, kw_only=True)
#class Returned[Return](Memo, Exception):
#    value: Return


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](_base.Context[Params, Return], abc.ABC):
    event: asyncio.Event | threading.Event
    memo: RowBase
    session: Session[Return]
    #session: sqlalchemy.ext.asyncio.AsyncSession | sqlalchemy.orm.Session


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContext[** Params, Return](Context[Params, Return], _base.AsyncContext[Params, Return]):
    event: asyncio.Event = dataclasses.field(default_factory=asyncio.Event)
    session: sqlalchemy.ext.asyncio.AsyncSession

    async def __call__(self, return_: Return) -> None:
        self.memo.value = return_
        self.session.add(self.memo)

    async def __aenter__(self) -> typing.Self:
        # Session should have already been started.
        # TODO lock the row
        #await self.session.begin()
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
        self.event.set()


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
    """Serves as the db."""
    duration: typing.Annotated[float, annotated_types.Ge(0.0)] | None
    #engine: sqlalchemy.ext.asyncio.AsyncEngine | sqlalchemy.Engine
    keygen: Keygen[Params]
    lock: asyncio.Lock | threading.Lock

    return_by_key: dict[Key, Context[Return] | Return] = dataclasses.field(default_factory=dict)
    return_by_key_by_instance: weakref.WeakKeyDictionary[
        _base.Instance, dict[Key, Context[Return] | Return]
    ] = dataclasses.field(default_factory=weakref.WeakKeyDictionary)

    row_t: type[RowBase]
    serializer: Serializer
    session_maker: sqlalchemy.orm.sessionmaker | sqlalchemy.ext.asyncio.async_sessionmaker
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

    @typing.overload
    def __get__(
        self: AsyncCreateContext[Params, Return],
        instance: _base.Instance,
        owner
    ) -> AsyncBoundCreateContext[Params, Return]: ...
    @typing.overload
    def __get__(
        self: MultiCreateContext[Params, Return],
        instance: _base.Instance,
        owner
    ) -> MultiBoundCreateContext[Params, Return]: ...
    def __get__(self, instance, owner):
        with self.lock:
            return self.BoundCreateContext[Params, Return](
                duration=self.duration,
                keygen=self.keygen,
                row_t=type('row', (RowBase,), {'__tablename__': f'{self.row_t.__tablename__}__{instance}'}),
                signature=self.signature,
                size=self.size,
            )


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncCreateContext[** Params, Return](CreateContext[Params, Return], _base.AsyncCreateContext[Params, Return]):
    engine: sqlalchemy.ext.asyncio.AsyncEngine
    lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)
    session_maker: sqlalchemy.ext.asyncio.async_sessionmaker

    BoundCreateContext: typing.ClassVar[type[AsyncBoundCreateContext]]
    Context: typing.ClassVar[type[AsyncContext]] = AsyncContext
    Session: typing.ClassVar[type[AsyncSession]] = AsyncSession

    async def __call__(self, args: Params.args, kwargs: Params.kwargs) -> AsyncContext[Params, Return] | Return:
        key = self.keygen(*args, **kwargs)

        async with self.lock:
            while (context := self.return_by_key.get(key)) is not None:
                match context:
                    case AsyncContext(event=event):
                        self.lock.release()
                        try:
                            await event.wait()
                        finally:
                            await self.lock.acquire()
                    case return_:
                        return return_

            session = self.session

            sessionmaker = sqlalchemy.ext.asyncio.async_sessionmaker(self.engine)

            context = self.Context(
                session=
            )

        connection = await sqlalchemy.ext.asyncio.AsyncConnection(self.engine)
        transaction = await connection.begin()
        try:
            transaction.add()
        finally:
            await transaction.rollback()

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
    lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    session_maker: sqlalchemy.orm.sessionmaker

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
    url: str = ':memory:'

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
                bound = signature.bind(*args, **kwargs)
                bound.apply_defaults()

                return bound.args, tuple(sorted(bound.kwargs))

        url = f'sqlite://{self.url}'

        match decoratee:
            case _base.AsyncDecorated():
                create_context_t = AsyncCreateContext
                engine = sqlalchemy.ext.asyncio.create_async_engine(url)
                session_maker = sqlalchemy.ext.asyncio.async_sessionmaker(
                    sqlalchemy.ext.asyncio.create_async_engine(url)
                )
            case _base.MultiDecorated():
                create_context_t = MultiCreateContext
                session_maker = sqlalchemy.orm.sessionmaker(
                    sqlalchemy.create_engine(url)
                )
            case _: assert False, 'Unreachable'

        create_context: CreateContext[Params, Return] = create_context_t(
            duration=self.duration,
            keygen=keygen,
            row_t=type[RowBase]('Row', (RowBase,), {'__tablename__': self.name.replace('.', '__')}),
            serializer=self.serializer,
            session_maker=session_maker,
            signature=signature,
            size=self.size,
        )

        decorated: _base.Decorated[Params, Return] = dataclasses.replace(
            decoratee, create_contexts=tuple([create_context, *decoratee.create_contexts])
        )

        decorated.register.decoratees[decorated.register_key] = decorated

        return decorated
