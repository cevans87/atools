from __future__ import annotations

import abc
import asyncio
import collections
import dataclasses
import inspect
import sys
import threading
import types
import typing
import weakref

from . import _base


type Expire = float
type Key = typing.Hashable
type Keygen[** Params] = typing.Callable[Params, Key]


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](_base.Context[Params, Return], abc.ABC):
    type context_t[** Params, Return] = type[AsyncContext[Params, Return]] | type[MultiContext[Params, Return]]
    type event_t = asyncio.Event | threading.Event
    type lock_t = asyncio.Lock | threading.Lock

    # FIXME: are args and kwargs used for anything?
    args: Params.args
    context_by_key: dict[Key, context_t[Params, Return]]
    event: event_t
    key: Key
    kwargs: Params.kwargs
    lock: lock_t
    return_by_key: typing.OrderedDict[Key, Return]
    signature: inspect.Signature
    size: int


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContext[** Params, Return](Context[Params, Return], _base.AsyncContext[Params, Return]):
    type context_t[** Params, Return] = AsyncContext[Params, Return]
    event_t: typing.ClassVar[type[asyncio.Event]] = asyncio.Event
    lock_t: typing.ClassVar[type[asyncio.Lock]] = asyncio.Lock

    context_by_key: dict[Key, context_t[Params, Return]]
    event: event_t = dataclasses.field(default_factory=event_t)
    lock: lock_t

    async def __call__(self, return_: Return) -> None:
        async with self.lock:
            self.return_by_key[self.key] = return_
            if len(self.return_by_key) > self.size:
                self.return_by_key.popitem(last=False)

    @typing.overload
    async def __aexit__[ExcType: type[BaseException]](
        self, exc_type: type[ExcType], exc_val: ExcType, exc_tb: types.TracebackType
    ) -> object: ...

    @typing.overload
    async def __aexit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None: ...

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with self.lock:
            self.context_by_key.pop(self.key)
        self.event.set()


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiContext[** Params, Return](Context[Params, Return], _base.MultiContext[Params, Return]):
    type context_t[** Params, Return] = MultiContext[Params, Return]
    event_t: typing.ClassVar[type[threading.Event]] = threading.Event
    lock_t: typing.ClassVar[type[asyncio.Lock]] = asyncio.Lock

    context_by_key: dict[Key, context_t[Params, Return]]
    event: event_t = dataclasses.field(default_factory=event_t)
    lock: lock_t

    def __call__(self, return_: Return) -> None:
        with self.lock:
            self.return_by_key[self.key] = return_
            if len(self.return_by_key) > self.size:
                self.return_by_key.popitem()

    @typing.overload
    def __exit__[ExcType: type[BaseException]](
        self, exc_type: type[ExcType], exc_val: ExcType, exc_tb: types.TracebackType
    ) -> object: ...

    @typing.overload
    def __exit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None: ...

    def __exit__(self, exc_type, exc_val, exc_tb):
        with self.lock:
            self.context_by_key.pop(self.key)
        self.event.set()


@dataclasses.dataclass(frozen=True, kw_only=True)
class CreateContext[** Params, Return](_base.CreateContext[Params, Return], abc.ABC):
    type context_t[** Params, Return] = type[AsyncContext[Params, Return]] | type[MultiCreateContext[Params, Return]]
    type lock_t = type[asyncio.Lock] | type[threading.Lock]

    keygen: Keygen[Params]
    lock: lock_t
    context_by_key: dict[Key, context_t[Params, Return]] = dataclasses.field(default_factory=dict)
    context_by_key_by_instance: weakref.WeakKeyDictionary[_base.Instance, dict[Key, context_t[Params, Return]]]
    return_by_key: typing.OrderedDict[Key, Return] = dataclasses.field(default_factory=collections.OrderedDict)
    return_by_key_by_instance: weakref.WeakKeyDictionary[
        _base.Instance, typing.OrderedDict[Key, Return]
    ] = dataclasses.field(default_factory=weakref.WeakKeyDictionary)
    signature: inspect.signature
    size: int

    def __get__(self, instance: _base.Instance, owner) -> CreateContext[Params, Return]:
        with self.instance_lock:
            return dataclasses.replace(
                self,
                context_by_key=self.context_by_key_by_instance.setdefault(instance, collections.OrderedDict()),
                instance=instance,
                return_by_key=self.return_by_key_by_instance.setdefault(instance, collections.OrderedDict()),
            )


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncCreateContext[** Params, Return](CreateContext[Params, Return], _base.AsyncCreateContext[Params, Return]):
    context_t: typing.ClassVar[type[AsyncContext]] = AsyncContext
    lock_t: typing.ClassVar[type[asyncio.Lock]] = asyncio.Lock

    context_by_key: dict[Key, context_t[Params, Return]] = dataclasses.field(default_factory=dict)
    context_by_key_by_instance: weakref.WeakKeyDictionary[
        _base.Instance, dict[Key, context_t[Params, Return]]
    ] = dataclasses.field(default_factory=weakref.WeakKeyDictionary)
    lock: lock_t = dataclasses.field(default_factory=lock_t)

    async def __call__(self, args: Params.args, kwargs: Params.kwargs) -> context_t[Params, Return] | Return:
        key = self.keygen(*args, **kwargs)
        async with self.lock:
            while (context := self.context_by_key.get(key)) is not None:
                self.lock.release()
                try:
                    await context.event.wait()
                finally:
                    await self.lock.acquire()

            if key in self.return_by_key:
                return self.return_by_key[key]

            context = self.context_by_key[key] = self.context_t[Params, Return](
                args=args,
                context_by_key=self.context_by_key,
                key=key,
                kwargs=kwargs,
                lock=self.lock,
                return_by_key=self.return_by_key,
                signature=self.signature,
                size=self.size,
            )

        return context


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiCreateContext[** Params, Return](CreateContext[Params, Return], _base.MultiCreateContext[Params, Return]):
    context_t:  typing.ClassVar[type[MultiContext]] = MultiContext
    lock_t: typing.ClassVar[type[threading.Lock]] = threading.Lock

    context_by_key: dict[Key, context_t[Params, Return]] = dataclasses.field(default_factory=dict)
    context_by_key_by_instance: weakref.WeakKeyDictionary[
        _base.Instance, dict[Key, context_t[Params, Return]]
    ] = dataclasses.field(default_factory=weakref.WeakKeyDictionary)
    lock: lock_t = dataclasses.field(default_factory=lock_t)

    def __call__(self, args: Params.args, kwargs: Params.kwargs) -> context_t[Params, Return] | Return:
        key = self.keygen(*args, **kwargs)
        with self.lock:
            while (context := self.context_by_key.get(key)) is not None:
                self.lock.release()
                try:
                    context.event.wait()
                finally:
                    self.lock.acquire()

            if key in self.return_by_key:
                return self.return_by_key[key]

            context = self.context_by_key[key] = self.context_t[Params, Return](
                args=args,
                context_by_key=self.context_by_key,
                key=key,
                kwargs=kwargs,
                lock=self.lock,
                return_by_key=self.return_by_key,
                signature=self.signature,
                size=self.size,
            )

        return context


@dataclasses.dataclass(frozen=True, kw_only=True)
class Decorator[** Params, Return]:
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
            decoratee = _base.Decorator[Params, Return]()(decoratee)

        signature = inspect.signature(decoratee.decoratee)
        if (keygen := self.keygen) is ...:
            def keygen(*args, **kwargs) -> typing.Hashable:
                bind = signature.bind(*args, **kwargs)
                bind.apply_defaults()

                return bind.args, tuple(sorted(bind.kwargs))

        match decoratee:
            case _base.AsyncDecorated():
                create_context_t = AsyncCreateContext
            case _base.MultiDecorated():
                create_context_t = MultiCreateContext
            case _: assert False, 'Unreachable'  # pragma: no cover

        create_context: CreateContext[Params, Return] = create_context_t(
            keygen=keygen,
            signature=signature,
            size=self.size,
        )

        decorated: _base.Decorated[Params, Return] = dataclasses.replace(
            decoratee, create_contexts=tuple([create_context, *decoratee.create_contexts])
        )

        decorated.register.decoratees[decorated.register_key] = decorated

        return decorated
