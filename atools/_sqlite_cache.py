from __future__ import annotations

import abc
import annotated_types
import asyncio
import collections
import dataclasses
import inspect
import json
import sys
import threading
import types
import typing
import weakref

import aiosqlite
import sqlite3

import sqlalchemy
import sqlalchemy.dialects.sqlite
import sqlalchemy.ext.asyncio
import sqlalchemy.orm

from . import _base


type Duration = float
type Expire = float
type Key = typing.Hashable
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
    __tablename__ = ''
    id: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(autoincrement=True, primary_key=True)
    key: sqlalchemy.orm.Mapped[str] = sqlalchemy.orm.mapped_column(index=True, unique=True)
    value: sqlalchemy.orm.Mapped[str] = sqlalchemy.orm.mapped_column()

    @classmethod
    @sqlalchemy.orm.declared_attr
    def __tablename__(cls) -> str:
        return cls.__name__


#class RowBase(Base):
#    __tablename__ = ''
#    id: sqlalchemy.orm.Mapped[int] = sqlalchemy.orm.mapped_column(autoincrement=True, primary_key=True)
#    key: sqlalchemy.orm.Mapped[str] = sqlalchemy.orm.mapped_column(index=True, unique=True)
#    value: sqlalchemy.orm.Mapped[str] = sqlalchemy.orm.mapped_column()
#
#    @classmethod
#    @sqlalchemy.orm.declared_attr
#    def __tablename__(cls) -> str:
#        return cls.__name__


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](_base.Context[Params, Return], abc.ABC):
    type context_t[** Params, Return] = type[AsyncContext[Params, Return]] | type[MultiContext[Params, Return]]
    type event_t = asyncio.Event | threading.Event
    type lock_t = asyncio.Lock | threading.Lock
    type session_t = sqlalchemy.ext.asyncio.AsyncSession | sqlalchemy.orm.Session

    context_by_key: dict[Key, context_t[Params, Return]]
    event: event_t
    key: Key
    lock: lock_t
    row_t: type[Base]
    serializer: Serializer
    session: session_t


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContext[** Params, Return](Context[Params, Return], _base.AsyncContext[Params, Return]):
    event_t: typing.ClassVar[type[asyncio.Event]] = asyncio.Event
    lock_t: typing.ClassVar[type[asyncio.Lock]] = asyncio.Lock

    event: event_t = dataclasses.field(default_factory=event_t)
    session: sqlalchemy.ext.asyncio.AsyncSession

    async def __call__(self, return_: Return) -> None:
        self.session.add(self.row_t(
            key=json.dumps({'key': self.key}),
            value=json.dumps({'return_': return_}))
        )

    async def __aenter__(self) -> typing.Self:
        await self.session.__aenter__()
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
        await self.session.__aexit__(exc_type, exc_val, exc_tb)
        async with self.lock:
            self.context_by_key.pop(self.key)
        self.event.set()


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiContext[** Params, Return](Context[Params, Return], _base.MultiContext[Params, Return]):
    session: sqlalchemy.orm.Session

    def __call__(self, return_: Return) -> None:
        self.session.add(self.row_t(
            key=json.dumps({'key': self.key}),
            value=json.dumps({'return_': return_}))
        )

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
            self.session.rollback()
        self.session.__exit__(exc_type, exc_val, exc_tb)
        with self.lock:
            self.context_by_key.pop(self.key)
        self.event.set()


@dataclasses.dataclass(frozen=True, kw_only=True)
class CreateContext[** Params, Return](_base.CreateContext[Params, Return], abc.ABC):
    type context_t[** Params, Return] = AsyncContext[Params, Return] | MultiContext[Params, Return]
    type engine_t = sqlalchemy.ext.asyncio.AsyncEngine | sqlalchemy.Engine

    context_by_key: dict[Key, context_t[Params, Return]]
    context_by_key_by_instance: weakref.WeakKeyDictionary[_base.Instance, dict[Key, context_t[Params, Return]]]
    engine: engine_t
    duration: typing.Annotated[float, annotated_types.Ge(0.0)] | None
    keygen: Keygen[Params]
    lock: asyncio.Lock | threading.Lock
    row_t: type[Base]
    serializer: Serializer
    session_maker: sqlalchemy.orm.sessionmaker | sqlalchemy.ext.asyncio.async_sessionmaker
    signature: inspect.signature
    size: int

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
    ) -> AsyncCreateContext[Params, Return]: ...

    @typing.overload
    def __get__(
        self: MultiCreateContext[Params, Return],
        instance: _base.Instance,
        owner
    ) -> MultiCreateContext[Params, Return]: ...

    def __get__(self, instance, owner):
        with self.lock:
            return dataclasses.replace(
                self,
                instance=instance,
                context_by_key=self.context_by_key_by_instance.setdefault(instance, collections.OrderedDict()),
                row_t=type[Base]('row', (Base,), {'__tablename__': f'{self.row_t.__tablename__}__{instance}'}),
            )


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncCreateContext[** Params, Return](CreateContext[Params, Return], _base.AsyncCreateContext[Params, Return]):
    context_t: typing.ClassVar[type[AsyncContext]] = AsyncContext
    engine_t: typing.ClassVar[type[sqlalchemy.ext.asyncio.AsyncEngine]] = sqlalchemy.ext.asyncio.AsyncEngine

    engine: engine_t
    context_by_key: dict[Key, context_t[Params, Return]] = dataclasses.field(default_factory=dict)
    context_by_key_by_instance: weakref.WeakKeyDictionary[
        _base.Instance, dict[Key, context_t[Params, Return]]
    ] = dataclasses.field(default_factory=weakref.WeakKeyDictionary)
    lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)
    session_maker: sqlalchemy.ext.asyncio.async_sessionmaker

    async def __call__(self, args: Params.args, kwargs: Params.kwargs) -> context_t[Params, Return] | Return:
        key = self.keygen(*args, **kwargs)
        async with self.lock:
            while (context := self.context_by_key.get(key)) is not None:
                self.lock.release()
                try:
                    await context.event.wait()
                finally:
                    await self.lock.acquire()

            async with self.session_maker.begin() as session:
                session.add(sqlalchemy.schema.CreateTable(self.row_t.metadata.schema, if_not_exists=True))
                self.row_t.metadata.create_all(session)
                #session.add(sqlalchemy.schema.CreateTable(sqlalchemy.inspect(self.row_t).local_table))
                if (row := (await session.execute(
                    sqlalchemy.select(self.row_t).where(self.row_t.key == json.dumps({'key': key}))
                )).one_or_none()) is not None:
                    return json.loads(row.value)['return_']

            context = self.context_by_key[key] = self.context_t[Params, Return](
                session=self.session_maker.begin()
            )

        return context


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiCreateContext[** Params, Return](CreateContext[Params, Return], _base.MultiCreateContext[Params, Return]):
    context_t: typing.ClassVar[type[MultiContext]] = MultiContext
    engine_t: sqlalchemy.Engine

    engine: engine_t
    context_by_key_by_instance: weakref.WeakKeyDictionary[
        _base.Instance, dict[Key, context_t[Params, Return]]
    ] = dataclasses.field(default_factory=weakref.WeakKeyDictionary)
    lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    session_maker: sqlalchemy.orm.sessionmaker

    def __call__(self, args: Params.args, kwargs: Params.kwargs) -> context_t[Params, Return] | Return:
        key = self.keygen(*args, **kwargs)
        with self.lock:
            while (context := self.context_by_key.get(key)) is not None:
                self.lock.release()
                try:
                    context.event.wait()
                finally:
                    self.lock.acquire()

            with self.session_maker.begin() as session:
                if (row := session.execute(
                    sqlalchemy.select(self.row_t).where(self.row_t.key == json.dumps({'key': key}))
                ).one_or_none()) is not None:
                    return json.loads(row.value)['return_']

            context = self.context_by_key[key] = self.context_t[Params, Return](
                session=self.session_maker.begin()
            )

        return context


@dataclasses.dataclass(frozen=True, kw_only=True)
class Decorator[** Params, Return]:
    duration: typing.Annotated[float, annotated_types.Ge(0.0)] | None = None
    keygen: Keygen[Params] = ...
    serializer: Serializer = ...
    size: int = sys.maxsize
    url: str = ''

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
            decoratee = _base.Decorator[Params, Return]()(decoratee)

        signature = inspect.signature(decoratee.decoratee)
        if (keygen := self.keygen) is ...:
            def keygen(*args, **kwargs) -> Key:
                bound = signature.bind(*args, **kwargs)
                bound.apply_defaults()

                return bound.args, tuple(sorted(bound.kwargs))

        match decoratee:
            case _base.AsyncDecorated():
                create_context_t = AsyncCreateContext
                engine = sqlalchemy.ext.asyncio.create_async_engine(f'sqlite+aiosqlite://{self.url}', echo=True)
                session_maker = sqlalchemy.ext.asyncio.async_sessionmaker(engine)
            case _base.MultiDecorated():
                create_context_t = MultiCreateContext
                engine = sqlalchemy.create_engine(f'sqlite://{self.url}', echo=True)
                session_maker = sqlalchemy.orm.sessionmaker(engine)
            case _: assert False, 'Unreachable'

        create_context: CreateContext[Params, Return] = create_context_t(
            duration=self.duration,
            engine=engine,
            keygen=keygen,
            row_t=type[Base]('Row', (Base,), {'__tablename__': '__'.join(decoratee.register_key)}),
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
