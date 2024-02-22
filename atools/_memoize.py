import asyncio
import collections
import dataclasses
import datetime
import functools
import hashlib
import inspect
import pathlib
import pickle
import sqlite3
import textwrap
import time
import threading
import typing
import weakref

from . import _context
from . import _key


Keygen = typing.Callable[..., object]


class Serializer(typing.Protocol):

    @staticmethod
    def dumps(_str: str) -> str: ...

    @staticmethod
    def loads(_bytes: bytes) -> object: ...


class MemoZeroValue:
    ...


@dataclasses.dataclass
class MemoReturnState:
    called: bool = False
    raised: bool = False
    value: object = MemoZeroValue


@dataclasses.dataclass(frozen=True, kw_only=True)
class MemoBase:
    t0: float | None
    memo_return_state: MemoReturnState = dataclasses.field(init=False, default_factory=MemoReturnState)


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncMemo(MemoBase):
    async_lock: asyncio.Lock = dataclasses.field(init=False, default_factory=lambda: asyncio.Lock())


@dataclasses.dataclass(frozen=True, kw_only=True)
class SyncMemo(MemoBase):
    sync_lock: threading.Lock = dataclasses.field(init=False, default_factory=lambda: threading.Lock())


_Memo = AsyncMemo | SyncMemo


@dataclasses.dataclass(frozen=True, kw_only=True)
class MemoizeBase[** Params, Return]:
    db: sqlite3.Connection | None
    default_kwargs: dict[str, object]
    duration: datetime.timedelta | None
    fn: typing.Callable
    keygen: Keygen | None
    serializer: Serializer = dataclasses.field(hash=False)
    size: int | None

    expire_order: collections.OrderedDict = dataclasses.field(
        init=False, default_factory=collections.OrderedDict, hash=False
    )
    memos: collections.OrderedDict = dataclasses.field(
        init=False, default_factory=collections.OrderedDict, hash=False
    )

    def __post_init__(self) -> None:
        if self.db is not None:
            self.db.isolation_level = None

            self.db.execute(textwrap.dedent(f'''
                CREATE TABLE IF NOT EXISTS `{self.table_name}` (
                  k TEXT PRIMARY KEY,
                  t0 FLOAT,
                  t FLOAT,
                  v TEXT NOT NULL
                )
            '''))
            if self.duration:
                self.db.execute(textwrap.dedent(f'''
                    DELETE FROM `{self.table_name}`
                    WHERE t0 < {time.time() - self.duration.total_seconds()}
                '''))

            if self.size:
                res = self.db.execute(
                    f"SELECT t FROM `{self.table_name}` ORDER BY t DESC LIMIT {self.size}"
                ).fetchall()
                if res:
                    (min_t,) = res[-1]
                    self.db.execute(f"DELETE FROM `{self.table_name}` WHERE t < {min_t}")
            for k, t0, t, v in self.db.execute(
                f"SELECT k, t0, t, v FROM `{self.table_name}` ORDER BY t"
            ).fetchall():
                memo = self.make_memo(t0=t0)
                memo.memo_return_state.called = True
                memo.memo_return_state.value = self.serializer.loads(v)
                self.memos[k] = memo
            if self.duration:
                for k, t0 in self.db.execute(
                        f"SELECT k, t0 FROM `{self.table_name}` ORDER BY t0"
                ).fetchall():
                    self.expire_order[k] = ...

    def __len__(self) -> int:
        return len(self.memos)

    @property
    def table_name(self) -> str:
        # noinspection PyUnresolvedReferences
        return (
            f'{self.fn.__code__.co_filename}'
            f':{self.fn.__code__.co_name}'
            f':{self.fn.__code__.co_firstlineno}'
        )

    def bind_key_lifetime(self, raw_key: typing.Tuple[object, ...], key: int | str) -> None:
        for raw_key_part in raw_key:
            if (raw_key_part is not None) and (type(raw_key_part).__hash__ is object.__hash__):
                weakref.finalize(raw_key_part, self.reset_key, key)

    def default_keygen(self, *args, **kwargs) -> typing.Tuple[typing.Hashable, ...]:
        """Returns all params (args, kwargs, and missing default kwargs) for function as kwargs."""

        return tuple(self.get_args_as_kwargs(*args, **kwargs).values())

    def get_args_as_kwargs(self, *args, **kwargs) -> collections.ChainMap[str, object]:
        args_as_kwargs = {}
        for k, v in zip(self.default_kwargs, args):
            args_as_kwargs[k] = v
        return collections.ChainMap(args_as_kwargs, kwargs, self.default_kwargs)

    def get_memo(self, key: int | str, insert: bool) -> _Memo | None:
        try:
            memo = self.memos[key] = self.memos.pop(key)
            if self.duration is not None and memo.t0 < time.time() - self.duration.total_seconds():
                self.expire_order.pop(key)
                raise ValueError('value expired')
        except (KeyError, ValueError):
            if not insert:
                return None
            elif self.duration is None:
                t0 = None
            else:
                t0 = time.time()
                # The value has no significance. We're using the dict entirely for ordering keys.
                self.expire_order[key] = ...

            memo = self.memos[key] = self.make_memo(t0=t0)

        return memo

    def expire_one_memo(self) -> None:
        k = None
        if (
                (self.expire_order is not None) and
                (len(self.expire_order) > 0) and
                (
                        self.memos[next(iter(self.expire_order))].t0 <
                        time.time() - self.duration.total_seconds()
                )
        ):
            (k, _) = self.expire_order.popitem(last=False)
            self.memos.pop(k)
        elif self.size is not None and self.size < len(self.memos):
            (k, _) = self.memos.popitem(last=False)
            if self.expire_order:
                self.expire_order.pop(k)
        if (self.db is not None) and (k is not None):
            self.db.execute(f"DELETE FROM `{self.table_name}` WHERE k = '{k}'")

    def finalize_memo(self, memo: _Memo, key: int | str) -> object:
        if memo.memo_return_state.raised:
            raise memo.memo_return_state.value
        elif (self.db is not None) and (self.memos[key] is memo):
            value = self.serializer.dumps(memo.memo_return_state.value)
            self.db.execute(
                textwrap.dedent(f'''
                    INSERT OR REPLACE INTO `{self.table_name}`
                    (k, t0, t, v)
                    VALUES
                    (?, ?, ?, ?)
                '''),
                (
                    key,
                    memo.t0,
                    time.time(),
                    value
                )
            )
        return memo.memo_return_state.value

    def get_key(self, raw_key: typing.Tuple[typing.Hashable, ...]) -> int | str:
        if self.db is None:
            key = hash(raw_key)
        else:
            key = hashlib.sha256(str(raw_key).encode()).hexdigest()

        return key

    @staticmethod
    def make_memo(t0: float | None) -> _Memo:  # pragma: no cover
        raise NotImplemented

    def reset(self) -> None:
        object.__setattr__(self, 'expire_order', collections.OrderedDict())
        object.__setattr__(self, 'memos', collections.OrderedDict())
        if self.db is not None:
            self.db.execute(f"DELETE FROM `{self.table_name}`")

    def reset_key(self, key: int | str) -> None:
        if key in self.memos:
            self.memos.pop(key)
            if self.duration is not None:
                self.expire_order.pop(key)
            if self.db is not None:
                self.db.execute(f"DELETE FROM `{self.table_name}` WHERE k == '{key}'")


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncDecoration[** Params, Return](MemoizeBase[Params, Return]):

    async def get_raw_key(self, *args, **kwargs) -> typing.Tuple[typing.Hashable, ...]:
        if self.keygen is None:
            raw_key = self.default_keygen(*args, **kwargs)
        else:
            raw_key = self.keygen(**self.get_args_as_kwargs(*args, **kwargs))
            if isinstance(raw_key, tuple):
                raw_key = list(raw_key)
            else:
                raw_key = [raw_key]

            for i, v in enumerate(raw_key):
                if inspect.isawaitable(v):
                    raw_key[i] = await v
            raw_key = tuple(raw_key)

        return raw_key

    def get_behavior(self, *, insert: bool, update: bool) -> typing.Callable:
        def get_call(*, fn: typing.Callable) -> typing.Callable:

            @functools.wraps(self.fn)
            async def call(*args, **kwargs) -> object:
                raw_key = await self.get_raw_key(*args, **kwargs)
                key = self.get_key(raw_key)

                memo: AsyncMemo = self.get_memo(key, insert=insert)
                if memo is None:
                    return await fn(*args, **kwargs)

                self.expire_one_memo()

                async with memo.async_lock:
                    if (
                            (insert and not memo.memo_return_state.called) or
                            (update and memo.memo_return_state.value is not MemoZeroValue)
                    ):
                        memo.memo_return_state.called = True
                        try:
                            memo.memo_return_state.value = await fn(*args, **kwargs)
                        except Exception as e:
                            memo.memo_return_state.raised = True
                            memo.memo_return_state.value = e

                        self.bind_key_lifetime(raw_key, key)

                    return self.finalize_memo(memo=memo, key=key)

            return call
        return get_call

    async def insert(self, *args, **kwargs) -> object:
        return await self.get_behavior(insert=True, update=False)(fn=self.fn)(*args, **kwargs)

    def update(self, *args, **kwargs) -> typing.Callable:

        async def to(value: object) -> object:
            async def fn(*_args, **_kwargs) -> object:
                return value

            return await self.get_behavior(insert=False, update=True)(fn=fn)(*args, **kwargs)

        return to

    def upsert(self, *args, **kwargs) -> typing.Callable:

        async def to(value: object) -> object:
            async def fn(*_args, **_kwargs) -> object:
                return value

            return await self.get_behavior(insert=True, update=True)(fn=fn)(*args, **kwargs)

        return to

    async def remove(self, *args, **kwargs) -> None:
        raw_key = await self.get_raw_key(*args, **kwargs)
        key = self.get_key(raw_key)
        self.reset_key(key)

    def get_decorator(self) -> typing.Callable:

        async def decorator(*args, **kwargs) -> object:
            return await self.insert(*args, **kwargs)

        decorator.memoize = self

        return decorator

    @staticmethod
    def make_memo(t0: float | None) -> AsyncMemo:
        return AsyncMemo(t0=t0)


@dataclasses.dataclass(frozen=True, kw_only=True)
class SyncDecoration[** Params, Return](MemoizeBase[Params, Return]):

    _sync_lock: threading.Lock = dataclasses.field(init=False, default_factory=lambda: threading.Lock())

    def get_raw_key(self, *args, **kwargs) -> typing.Tuple[typing.Hashable, ...]:
        if self.keygen is None:
            raw_key = self.default_keygen(*args, **kwargs)
        else:
            raw_key = self.keygen(**self.get_args_as_kwargs(*args, **kwargs))
            if not isinstance(raw_key, tuple):
                raw_key = [raw_key]
            raw_key = tuple(raw_key)

        return raw_key

    def get_behavior(self, *, insert: bool, update: bool) -> typing.Callable:
        def get_call(*, fn: typing.Callable) -> typing.Callable:

            @functools.wraps(self.fn)
            def call(*args, **kwargs) -> object:
                raw_key = self.get_raw_key(*args, **kwargs)
                key = self.get_key(raw_key)

                with self._sync_lock:
                    memo: SyncMemo = self.get_memo(key, insert=insert)
                    if memo is None:
                        return fn(*args, **kwargs)

                self.expire_one_memo()

                with memo.sync_lock:
                    if (
                            (insert and not memo.memo_return_state.called) or
                            (update and memo.memo_return_state.value is not MemoZeroValue)
                    ):
                        memo.memo_return_state.called = True
                        try:
                            memo.memo_return_state.value = fn(*args, **kwargs)
                        except Exception as e:
                            memo.memo_return_state.raised = True
                            memo.memo_return_state.value = e

                        self.bind_key_lifetime(raw_key, key)

                    return self.finalize_memo(memo=memo, key=key)

            return call

        return get_call

    def insert(self, *args, **kwargs) -> object:
        return self.get_behavior(insert=True, update=False)(fn=self.fn)(*args, **kwargs)

    def update(self, *args, **kwargs) -> typing.Callable:

        def to(value: object) -> object:
            def fn(*_args, **_kwargs) -> object:
                return value

            return self.get_behavior(insert=False, update=True)(fn=fn)(*args, **kwargs)

        return to

    def upsert(self, *args, **kwargs) -> typing.Callable:

        def to(value: object) -> object:
            def fn(*_args, **_kwargs) -> object:
                return value

            return self.get_behavior(insert=True, update=True)(fn=fn)(*args, **kwargs)

        return to

    def remove(self, *args, **kwargs) -> None:
        raw_key = self.get_raw_key(*args, **kwargs)
        key = self.get_key(raw_key)
        self.reset_key(key)

    def get_decorator(self) -> typing.Callable:

        def decorator(*args, **kwargs) -> object:
            return self.insert(*args, **kwargs)

        decorator.memoize = self

        return decorator

    @staticmethod
    def make_memo(t0: float | None) -> SyncMemo:
        return SyncMemo(t0=t0)

    def reset(self) -> None:
        with self._sync_lock:
            super().reset()

    def reset_key(self, key: int | str) -> None:
        with self._sync_lock:
            super().reset_key(key)


type Decoration[** Params, Return] = AsyncDecoration[Params, Return] | SyncDecoration[Params, Return]


class AsyncDecoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, Return]


class SyncDecoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, Return]


type Decoratee[** Params, Return] = AsyncDecoratee[Params, Return] | SyncDecoratee[Params, Return]


class AsyncDecorated[** Params, Return](AsyncDecoratee[Params, Return], _context.AsyncDecorated):
    memoize: Decoration[Params, Return]


class SyncDecorated[** Params, Return](SyncDecoratee[Params, Return], _context.SyncDecorated):
    memoize: Decoration[Params, Return]


type Decorated[** Params, Return] = AsyncDecorated[Params, Return] | SyncDecorated[Params, Return]


@dataclasses.dataclass(frozen=True)
class Decorator:
    """Decorates a function call and caches return value for given inputs.
    - If `db_path` is provided, memos will persist on disk and reloaded during initialization.
    - If `duration` is provided, memos will only be valid for given `duration`.
    - If `keygen` is provided, memo hash keys will be created with given `keygen`.
    - If `pickler` is provided, persistent memos will (de)serialize using given `pickler`.
    - If `size` is provided, LRU memo will be evicted if current count exceeds given `size`.

    ### Examples

    - Body will run once for unique input `bar` and result is cached.
        ```python3
        @memoize
        def foo(bar) -> object: ...

        foo(1)  # Function actually called. Result cached.
        foo(1)  # Function not called. Cached result returned.
        foo(2)  # Function actually called. Result cached.
        ```

    - Same as above, but async.
        ```python3
        @memoize
        async def foo(bar) -> object: ...

        # Concurrent calls from the same event loop are safe. Only one call is generated. The
        # other nine calls in this example wait for the result.
        await asyncio.gather(*[foo(1) for _ in range(10)])
        ```

    - Classes may be memoized.
        ```python3
        @memoize
        Class Foo:
            def init(self, _): ...

        Foo(1)  # Instance is actually created.
        Foo(1)  # Instance not created. Cached instance returned.
        Foo(2)  # Instance is actually created.
        ```

    - Calls `foo(1)`, `foo(bar=1)`, and `foo(1, baz='baz')` are equivalent and only cached once.
        ```python3
        @memoize
        def foo(bar, baz='baz'): ...
        ```

    - Only 2 items are cached. Acts as an LRU.
        ```python3
        @memoize(size=2)
        def foo(bar) -> object: ...

        foo(1)  # LRU cache order [foo(1)]
        foo(2)  # LRU cache order [foo(1), foo(2)]
        foo(1)  # LRU cache order [foo(2), foo(1)]
        foo(3)  # LRU cache order [foo(1), foo(3)], foo(2) is evicted to keep cache size at 2
        ```

    - Items are evicted after 1 minute.
        ```python3
        @memoize(duration=datetime.timedelta(minutes=1))
        def foo(bar) -> object: ...

        foo(1)  # Function actually called. Result cached.
        foo(1)  # Function not called. Cached result returned.
        sleep(61)
        foo(1)  # Function actually called. Cached result was too old.
        ```

    - Memoize can be explicitly reset through the function's `.memoize` attribute
        ```python3
        @memoize
        def foo(bar) -> object: ...

        foo(1)  # Function actually called. Result cached.
        foo(1)  # Function not called. Cached result returned.
        foo.memoize.reset()
        foo(1)  # Function actually called. Cache was emptied.
        ```

    - Current cache length can be accessed through the function's `.memoize` attribute
        ```python3
        @memoize
        def foo(bar) -> object: ...

        foo(1)
        foo(2)
        len(foo.memoize)  # returns 2
        ```

    - Alternate memo hash function can be specified. The inputs must match the function's.
        ```python3
        Class Foo:
            @memoize(keygen=lambda self, a, b, c: (a, b, c))  # Omit 'self' from hash key.
            def bar(self, a, b, c) -> object: ...

        a, b = Foo(), Foo()

        # Hash key will be (a, b, c)
        a.bar(1, 2, 3)  # LRU cache order [Foo.bar(a, 1, 2, 3)]

        # Hash key will again be (a, b, c)
        # Be aware, in this example the returned result comes from a.bar(...), not b.bar(...).
        b.bar(1, 2, 3)  # Function not called. Cached result returned.
        ```

    - If part of the returned key from keygen is awaitable, it will be awaited.
        ```python3
        async def awaitable_key_part() -> typing.Hashable: ...

        @memoize(keygen=lambda bar: (bar, awaitable_key_part()))
        async def foo(bar) -> object: ...
        ```

    - If the memoized function is async and any part of the key is awaitable, it is awaited.
        ```python3
        async def morph_a(a: int) -> int: ...

        @memoize(keygen=lambda a, b, c: (morph_a(a), b, c))
        def foo(a, b, c) -> object: ...
        ```

    - Properties can be memoized.
        ```python3
        Class Foo:
            @property
            @memoize
            def bar(self) -> object: ...

        a = Foo()
        a.bar  # Function actually called. Result cached.
        a.bar  # Function not called. Cached result returned.

        b = Foo() # Memoize uses 'self' parameter in hash. 'b' does not share returns with 'a'
        b.bar  # Function actually called. Result cached.
        b.bar  # Function not called. Cached result returned.
        ```

    - Be careful with eviction on instance methods. Memoize is not instance-specific.
        ```python3
        Class Foo:
            @memoize(size=1)
            def bar(self, baz) -> object: ...

        a, b = Foo(), Foo()
        a.bar(1)  # LRU cache order [Foo.bar(a, 1)]
        b.bar(1)  # LRU cache order [Foo.bar(b, 1)], Foo.bar(a, 1) is evicted
        a.bar(1)  # Foo.bar(a, 1) is actually called and cached again.
        ```

    - Values can persist to disk and be reloaded when memoize is initialized again.
        ```python3
        @memoize(db_path=pathlib.Path.home() / '.memoize')
        def foo(a) -> object: ...

        foo(1)  # Function actually called. Result cached.

        # Process is restarted. Upon restart, the state of the memoize decorator is reloaded.

        foo(1)  # Function not called. Cached result returned.
        ```

    - If not applied to a function, calling the decorator returns a partial application.
        ```python3
        memoize_db = memoize(db_path=pathlib.Path.home() / '.memoize')

        @memoize_db(size=1)
        def foo(a) -> object: ...

        @memoize_db(duration=datetime.timedelta(hours=1))
        def bar(b) -> object: ...
        ```

    - Comparison equality does not affect memoize. Only hash equality matters.
        ```python3
        # Inherits object.__hash__
        class Foo:
            # Don't be fooled. memoize only cares about the hash.
            def __eq__(self, other: Foo) -> bool:
                return True

        @memoize
        def bar(foo: Foo) -> object: ...

        foo0, foo1 = Foo(), Foo()
        assert foo0 == foo1
        bar(foo0)  # Function called. Result cached.
        bar(foo1)  # Function called again, despite equality, due to different hash.
        ```

    ### A warning about arguments that inherit `object.__hash__`:

    It doesn't make sense to keep a memo if it's impossible to generate the same input again. Inputs
    that inherit the default `object.__hash__` are unique based on their id, and thus, their
    location in memory. If such inputs are garbage-collected, they are gone forever. For that
    reason, when those inputs are garbage collected, `memoize` will drop memos created using those
    inputs.

    - Memo lifetime is bound to the lifetime of any arguments that inherit `object.__hash__`.
        ```python3
        # Inherits object.__hash__
        class Foo:
            ...

        @memoize
        def bar(foo: Foo) -> object: ...

        bar(Foo())  # Memo is immediately deleted since Foo() is garbage collected.

        foo = Foo()
        bar(foo)  # Memo isn't deleted until foo is deleted.
        del foo  # Memo is deleted at the same time as foo.
        ```

    - Types that have specific, consistent hash functions (int, str, etc.) won't cause problems.
        ```python3
        @memoize
        def foo(a: int, b: str, c: Tuple[int, ...], d: range) -> object: ...

        foo(1, 'bar', (1, 2, 3), range(42))  # Function called. Result cached.
        foo(1, 'bar', (1, 2, 3), range(42))  # Function not called. Cached result returned.
        ```

    - Classmethods rely on classes, which inherit from `object.__hash__`. However, classes are
      almost never garbage collected until a process exits so memoize will work as expected.

        ```python3
        class Foo:
          @classmethod
          @memoize
          def bar(cls) -> object: ...

        foo = Foo()
        foo.bar()  # Function called. Result cached.
        foo.bar()  # Function not called. Cached result returned.

        del foo  # Memo not cleared since lifetime is bound to class Foo.

        foo = Foo()
        foo.bar()  # Function not called. Cached result returned.
        foo.bar()  # Function not called. Cached result returned.
        ```

    - Long-lasting object instances that inherit from `object.__hash__`.

        ```python3
        class Foo:

            @memoize
            def bar(self) -> object: ...

        foo = Foo()
        foo.bar()  # Function called. Result cached.

        # foo instance is kept around somewhere and used later.
        foo.bar()  # Function not called. Cached result returned.
        ```

    - Custom pickler may be specified for unpickleable return types.

        ```python3
        import dill

        @memoize(db_path='~/.memoize`, pickler=dill)
        def foo() -> typing.Callable[[], None]:
            return lambda: None
        ```
    """

    _prefix: _key.Name = ...
    _suffix: _key.Name = ...
    db_path: pathlib.Path | None = None
    duration: int | float | datetime.timedelta | None = None
    keygen: Keygen | None = None
    serializer: Serializer | None = None
    size: int | None = None

    _all_decorators: typing.ClassVar[weakref.WeakSet] = weakref.WeakSet()

    @typing.overload
    def __call__[** Params, Return](
        self, decoratee: AsyncDecoratee[Params, Return], /
    ) -> AsyncDecorated[Params, Return]: ...

    @typing.overload
    def __call__[** Params, Return](
        self, decoratee: SyncDecoratee[Params, Return], /
    ) -> SyncDecorated[Params, Return]: ...

    def __call__[** Params, Return](self, decoratee: Decoratee[Params, Return], /) -> Decorated[Params, Return]:
        decoratee = _key.Decorator(self._prefix, self._suffix)(decoratee)

        db = sqlite3.connect(f'{self.db_path}') if self.db_path is not None else None
        duration = datetime.timedelta(seconds=self.duration) if isinstance(
            self.duration, (int, float)
        ) else self.duration
        assert (duration is None) or (duration.total_seconds() > 0)
        serializer = pickle if self.serializer is None else self.serializer
        assert (self.size is None) or (self.size > 0)
        default_kwargs: dict[str, object] = {
            k: v.default for k, v in inspect.signature(decoratee).parameters.items()
        }

        if inspect.iscoroutinefunction(decoratee):
            decoration_cls = AsyncDecoration
        else:
            decoration_cls = SyncDecoration

        # noinspection PyArgumentList
        decorator = decoration_cls(
            db=db,
            default_kwargs=default_kwargs,
            duration=duration,
            fn=decoratee,
            keygen=self.keygen,
            serializer=serializer,
            size=self.size,
        ).get_decorator()

        self._all_decorators.add(decorator)

        return functools.wraps(decoratee)(decorator)

    @classmethod
    def reset_all(cls) -> None:
        for decorator in cls._all_decorators:
            decorator.memoize.reset()
