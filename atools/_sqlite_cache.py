from __future__ import annotations

import abc
import annotated_types
import ast
import asyncio
import collections
import dataclasses
import inspect
import pathlib
import sys
import textwrap
import threading
import types
import typing
import weakref

import aiosqlite
import sqlite3

from . import _base


type Duration = float
type Expire = float
type Key = typing.Hashable
type Keygen[** Params] = typing.Callable[Params, Key]
type Value = object

type DeserializeValue[Return] = typing.Callable[[bytes], Return]
type SerializeKey[** Params] = typing.Callable[Params, bytes]
type SerializeValue[Return] = typing.Callable[[Return], bytes]


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](_base.Context[Params, Return], abc.ABC):
    type connection_t = aiosqlite.Connection | sqlite3.Connection
    type context_t[** Params, Return] = type[AsyncContext[Params, Return]] | type[MultiContext[Params, Return]]
    type event_t = asyncio.Event | threading.Event
    type lock_t = asyncio.Lock | threading.Lock

    connection: connection_t
    context_by_key: dict[Key, context_t[Params, Return]]
    event: event_t
    key: Key
    lock: lock_t
    serialize_key: SerializeKey[Params]
    serialize_value: SerializeValue[Return]
    table_name: str


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContext[** Params, Return](Context[Params, Return], _base.AsyncContext[Params, Return]):
    connection_t: typing.ClassVar[aiosqlite.Connection]
    event_t: typing.ClassVar[type[asyncio.Event]] = asyncio.Event
    lock_t: typing.ClassVar[type[asyncio.Lock]] = asyncio.Lock

    connection: connection_t
    context_by_key: dict[Key, AsyncContext[Params, Return]]
    event: event_t = dataclasses.field(default_factory=event_t)

    async def __call__(self, return_: Return) -> None:
        await self.connection.execute(
            f'''INSERT OR REPLACE INTO `{self.table_name}` (key, value) VALUES (?, ?)''',
            (self.serialize_key(self.key), self.serialize_value(return_))
        )

    async def __aenter__(self) -> typing.Self:
        return self

    @typing.overload
    async def __aexit__[ExcType: type[BaseException]](
        self, exc_type: type[ExcType], exc_val: ExcType, exc_tb: types.TracebackType
    ) -> object: ...

    @typing.overload
    async def __aexit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None: ...

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.connection.close()
        async with self.lock:
            self.context_by_key.pop(self.key)
        self.event.set()


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiContext[** Params, Return](Context[Params, Return], _base.MultiContext[Params, Return]):
    connection_t: typing.ClassVar[sqlite3.Connection]
    event_t: typing.ClassVar[type[threading.Event]] = threading.Event

    connection: connection_t
    context_by_key: dict[Key, MultiContext[Params, Return]]
    event: event_t = dataclasses.field(default_factory=event_t)

    def __call__(self, return_: Return) -> None:
        ...

    def __enter__(self) -> typing.Self:
        ...
        return self

    @typing.overload
    def __exit__[ExcType: type[BaseException]](
        self, exc_type: type[ExcType], exc_val: ExcType, exc_tb: types.TracebackType
    ) -> object: ...

    @typing.overload
    def __exit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None: ...

    def __exit__(self, exc_type, exc_val, exc_tb):
        ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class CreateContext[** Params, Return](_base.CreateContext[Params, Return], abc.ABC):
    type context_t[** Params, Return] = AsyncContext[Params, Return] | MultiContext[Params, Return]

    context_by_key: dict[Key, context_t[Params, Return]]
    context_by_key_by_instance: weakref.WeakKeyDictionary[_base.Instance, dict[Key, context_t[Params, Return]]]
    db_path: str
    deserialize_value: DeserializeValue[Return]
    keygen: Keygen[Params]
    lock: asyncio.Lock | threading.Lock
    serialize_key: SerializeKey[Params]
    serialize_value: SerializeValue[Return]
    size: int
    table_name: str

    def __post_init__(self) -> None:
        with sqlite3.connect(self.db_path, isolation_level=None) as connection:
            connection.execute(textwrap.dedent(f'''
                CREATE TABLE IF NOT EXISTS `{self.table_name}` (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key STRING NOT NULL UNIQUE,
                    VALUE STRING NOT NULL
                )
            '''))
            connection.execute(textwrap.dedent(f'''
                CREATE INDEX IF NOT EXISTS key_index ON `{self.table_name}` (value)
            '''))

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
        with self.instance_lock:
            return dataclasses.replace(
                self,
                instance=instance,
                context_by_key=self.context_by_key_by_instance.setdefault(instance, collections.OrderedDict()),
                table_name=f'{self.table_name}__{instance}',
            )


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncCreateContext[** Params, Return](CreateContext[Params, Return], _base.AsyncCreateContext[Params, Return]):
    context_t: typing.ClassVar[type[AsyncContext]] = AsyncContext

    context_by_key: dict[Key, context_t[Params, Return]] = dataclasses.field(default_factory=dict)
    context_by_key_by_instance: weakref.WeakKeyDictionary[
        _base.Instance, dict[Key, context_t[Params, Return]]
    ] = dataclasses.field(default_factory=weakref.WeakKeyDictionary)
    lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)

    async def __call__(self, args: Params.args, kwargs: Params.kwargs) -> context_t[Params, Return] | Return:
        key = self.keygen(*args, **kwargs)
        async with self.lock:
            while (context := self.context_by_key.get(key)) is not None:
                self.lock.release()
                try:
                    await context.event.wait()
                finally:
                    await self.lock.acquire()

            async with (
                aiosqlite.connect(self.db_path, isolation_level=None) as connection,
                await connection.execute(f'SELECT value FROM `{self.table_name}` WHERE key = ?', (repr(key),)) as cursor
            ):
                match await cursor.fetchall():
                    case [[value]]:
                        return ast.literal_eval(value)

            context = self.context_by_key[key] = self.context_t[Params, Return](
                connection=await aiosqlite.connect(self.db_path, isolation_level=None),
                context_by_key=self.context_by_key,
                key=key,
                lock=self.lock,
                serialize_key=self.serialize_key,
                serialize_value=self.serialize_value,
                table_name=self.table_name,
            )

        return context


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiCreateContext[** Params, Return](CreateContext[Params, Return], _base.MultiCreateContext[Params, Return]):
    context_t: typing.ClassVar[type[MultiContext]] = MultiContext

    context_by_key: dict[Key, context_t[Params, Return]] = dataclasses.field(default_factory=dict)
    context_by_key_by_instance: weakref.WeakKeyDictionary[
        _base.Instance, dict[Key, context_t[Params, Return]]
    ] = dataclasses.field(default_factory=weakref.WeakKeyDictionary)
    lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)

    def __call__(self, args: Params.args, kwargs: Params.kwargs) -> context_t[Params, Return] | Return:
        ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class Decorator[** Params, Return]:
    db_path: pathlib.Path | str = 'file::memory:?cache=shared'
    deserialize_value: DeserializeValue[Return] = ast.literal_eval
    duration: typing.Annotated[float, annotated_types.Ge(0.0)] | None = None
    keygen: Keygen[Params] = ...
    serialize_key: SerializeKey[Params] = repr
    serialize_value: SerializeValue[Return] = repr
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
            case _base.MultiDecorated():
                create_context_t = MultiCreateContext
            case _: assert False, 'Unreachable'

        create_context: CreateContext[Params, Return] = create_context_t(
            db_path=self.db_path,
            deserialize_value=self.deserialize_value,
            keygen=keygen,
            serialize_key=self.serialize_key,
            serialize_value=self.serialize_value,
            size=self.size,
            table_name='__'.join(decoratee.register_key),
        )

        decorated: _base.Decorated[Params, Return] = dataclasses.replace(
            decoratee, create_contexts=tuple([create_context, *decoratee.create_contexts])
        )

        decorated.register.decoratees[decorated.register_key] = decorated

        return decorated
