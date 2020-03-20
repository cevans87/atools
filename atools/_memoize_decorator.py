from asyncio import Lock as AsyncLock
from collections import ChainMap, OrderedDict
from dataclasses import dataclass, field
from datetime import timedelta
from functools import partial, wraps
from hashlib import sha256
import inspect
from pathlib import Path
import pickle
from sqlite3 import connect, Connection
from textwrap import dedent
from time import time
from threading import Lock as SyncLock
from typing import Any, Callable, Hashable, Mapping, Optional, Tuple, Type, Union
from weakref import finalize, WeakSet


Decoratee = Union[Callable, Type]
Keygen = Callable[..., Any]


class _MemoZeroValue:
    pass


@dataclass
class _MemoReturnState:
    called: bool = False
    raised: bool = False
    value: Any = _MemoZeroValue


@dataclass(frozen=True)
class _MemoBase:
    fn: Callable
    t0: Optional[float]
    memo_return_state: _MemoReturnState = field(init=False, default_factory=_MemoReturnState)


@dataclass(frozen=True)
class _AsyncMemo(_MemoBase):
    async_lock: AsyncLock = field(init=False, default_factory=lambda: AsyncLock())


@dataclass(frozen=True)
class _SyncMemo(_MemoBase):
    sync_lock: AsyncLock = field(init=False, default_factory=lambda: SyncLock())


_Memo = Union[_AsyncMemo, _SyncMemo]


@dataclass(frozen=True)
class _MemoizeBase:
    db: Optional[Connection]
    default_kwargs: Mapping[str, Any]
    duration: Optional[timedelta]
    fn: Callable
    keygen: Optional[Keygen]
    size: Optional[int]

    expire_order: OrderedDict = field(init=False, default_factory=OrderedDict, hash=False)
    memos: OrderedDict = field(init=False, default_factory=OrderedDict, hash=False)

    def __post_init__(self) -> None:
        if self.db is not None:
            self.db.isolation_level = None

            self.db.execute(dedent(f'''
                CREATE TABLE IF NOT EXISTS `{self.table_name}` (
                  k TEXT PRIMARY KEY,
                  t0 FLOAT,
                  t FLOAT,
                  v TEXT NOT NULL
                )
            '''))
            if self.duration:
                self.db.execute(dedent(f'''
                    DELETE FROM `{self.table_name}`
                    WHERE t0 < {time() - self.duration.total_seconds()}
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
                memo = self.make_memo(fn=self.fn, t0=t0)
                memo.memo_return_state.called = True
                memo.memo_return_state.value = pickle.loads(v)
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

    def bind_key_lifetime(self, raw_key: Tuple[Any, ...], key: Union[int, str]) -> None:
        for raw_key_part in raw_key:
            if type(raw_key_part).__hash__ is object.__hash__:
                finalize(raw_key_part, self.reset_key, key)

    def default_keygen(self, *args, **kwargs) -> Tuple[Hashable, ...]:
        """Returns all params (args, kwargs, and missing default kwargs) for function as kwargs."""

        return tuple(self.get_args_as_kwargs(*args, **kwargs).values())

    def get_args_as_kwargs(self, *args, **kwargs) -> Mapping[str, Any]:
        args_as_kwargs = {}
        for k, v in zip(self.default_kwargs, args):
            args_as_kwargs[k] = v
        return ChainMap(args_as_kwargs, kwargs, self.default_kwargs)

    def get_memo(self, key: Union[int, str]) -> _Memo:
        try:
            memo = self.memos[key] = self.memos.pop(key)
            if self.duration is not None and memo.t0 < time() - self.duration.total_seconds():
                self.expire_order.pop(key)
                raise ValueError('value expired')
        except (KeyError, ValueError):
            if self.duration is None:
                t0 = None
            else:
                t0 = time()
                # The value has no significance. We're using the dict entirely for ordering keys.
                self.expire_order[key] = ...

            memo = self.memos[key] = self.make_memo(self.fn, t0=t0)

        return memo

    def expire_one_memo(self) -> None:
        k = None
        if (
                (self.expire_order is not None) and
                (len(self.expire_order) > 0) and
                (
                        self.memos[next(iter(self.expire_order))].t0 <
                        time() - self.duration.total_seconds()
                )
        ):
            (k, _) = self.expire_order.popitem(last=False)
            self.memos.pop(k)
        elif self.size is not None and self.size < len(self.memos):
            (k, _) = self.memos.popitem(last=False)
        if (self.db is not None) and (k is not None):
            self.db.execute(f"DELETE FROM `{self.table_name}` WHERE k = '{k}'")

    def finalize_memo(self, memo: _Memo, key: Union[int, str]) -> Any:
        if memo.memo_return_state.raised:
            raise memo.memo_return_state.value
        else:
            if (self.db is not None) and (self.memos[key] is memo):
                value = pickle.dumps(memo.memo_return_state.value)
                self.db.execute(
                    dedent(f'''
                        INSERT OR REPLACE INTO `{self.table_name}`
                        (k, t0, t, v)
                        VALUES
                        (?, ?, ?, ?)
                    '''),
                    (
                        key,
                        memo.t0,
                        time(),
                        value
                    )
                )
            return memo.memo_return_state.value

    def get_key(self, raw_key: Tuple[Hashable, ...]) -> Union[int, str]:
        if self.db is None:
            key = hash(raw_key)
        else:
            key = sha256(str(raw_key).encode()).hexdigest()

        return key

    @staticmethod
    def make_memo(fn, t0: Optional[float]) -> _Memo:  # pragma: no cover
        raise NotImplemented
    
    def reset(self) -> None:
        object.__setattr__(self, 'expire_order', OrderedDict())
        object.__setattr__(self, 'memos', OrderedDict())
        if self.db is not None:
            self.db.execute(f"DELETE FROM `{self.table_name}`")

    def reset_key(self, key: Union[int, str]) -> None:
        if key in self.memos:
            self.memos.pop(key)
            if self.duration is not None:
                self.expire_order.pop(key)
            if self.db is not None:
                self.db.execute(f"DELETE FROM `{self.table_name}` WHERE k == '{key}'")


@dataclass(frozen=True)
class _AsyncMemoize(_MemoizeBase):

    async def get_raw_key(self, *args, **kwargs) -> Tuple[Hashable, ...]:
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

    def get_decorator(self) -> Callable:
        async def decorator(*args, **kwargs) -> Any:
            raw_key = await self.get_raw_key(*args, **kwargs)
            key = self.get_key(raw_key)

            memo: _AsyncMemo = self.get_memo(key)

            self.expire_one_memo()

            async with memo.async_lock:
                if not memo.memo_return_state.called:
                    memo.memo_return_state.called = True
                    try:
                        memo.memo_return_state.value = await memo.fn(*args, **kwargs)
                    except Exception as e:
                        memo.memo_return_state.raised = True
                        memo.memo_return_state.value = e

                    self.bind_key_lifetime(raw_key, key)

                return self.finalize_memo(memo=memo, key=key)

        decorator.memoize = self

        return decorator

    @staticmethod
    def make_memo(fn, t0: Optional[float]) -> _AsyncMemo:
        return _AsyncMemo(fn=fn, t0=t0)

    async def reset_call(self, *args, **kwargs) -> None:
        raw_key = await self.get_raw_key(*args, **kwargs)
        key = self.get_key(raw_key)
        self.reset_key(key)


@dataclass(frozen=True)
class _SyncMemoize(_MemoizeBase):

    _sync_lock: SyncLock = field(init=False, default_factory=lambda: SyncLock())
    
    def get_raw_key(self, *args, **kwargs) -> Tuple[Hashable, ...]:
        if self.keygen is None:
            raw_key = self.default_keygen(*args, **kwargs)
        else:
            raw_key = self.keygen(**self.get_args_as_kwargs(*args, **kwargs))
            if not isinstance(raw_key, tuple):
                raw_key = [raw_key]
            raw_key = tuple(raw_key)

        return raw_key

    def get_decorator(self) -> Callable:
        def decorator(*args, **kwargs):
            raw_key = self.get_raw_key(*args, **kwargs)
            key = self.get_key(raw_key)

            with self._sync_lock:
                memo: _SyncMemo = self.get_memo(key)

            self.expire_one_memo()

            with memo.sync_lock:
                if not memo.memo_return_state.called:
                    memo.memo_return_state.called = True
                    try:
                        memo.memo_return_state.value = memo.fn(*args, **kwargs)
                    except Exception as e:
                        memo.memo_return_state.raised = True
                        memo.memo_return_state.value = e

                    self.bind_key_lifetime(raw_key, key)

                return self.finalize_memo(memo=memo, key=key)

        decorator.memoize = self
                
        return decorator

    @staticmethod
    def make_memo(fn, t0: Optional[float]) -> _SyncMemo:
        return _SyncMemo(fn=fn, t0=t0)

    def reset(self) -> None:
        with self._sync_lock:
            super().reset()

    def reset_call(self, *args, **kwargs) -> None:
        raw_key = self.get_raw_key(*args, **kwargs)
        key = self.get_key(raw_key)
        self.reset_key(key)

    def reset_key(self, key: Union[int, str]) -> None:
        with self._sync_lock:
            super().reset_key(key)


class _Memoize:
    """Decorates a function call and caches return value for given inputs.

    If 'db' is provided, memoized values will be saved to disk and reloaded during initialization.

    If 'duration' is provided, memoize will only retain return values for up to given 'duration'.

    If 'keygen' is provided, memoize will use the function to calculate the memoize hash key.

    If 'size' is provided, memoize will only retain up to 'size' return values.

    A warning about arguments inheriting `object.__hash__`:

        It doesn't make sense to keep a memo if it's impossible to generate the same input again.
        Inputs that inherit the default `object.__hash__` are unique based on their id, and thus,
        their location in memory. If such inputs are garbage-collected, they are assumed to be gone
        forever. For that reason, when those inputs are garbage collected, `memoize` will drop memos
        created using those inputs.

        Here are some common patterns where this behaviour will not cause any problems.

            - Basic immutable types that have specific, consistent hash functions (int, str, etc.).
                @memoize
                def foo(a: int, b: str, c: Tuple[int, ...], d: range) -> Any: ...

                foo(1, 'bar', (1, 2, 3), range(42))  # Function called. Result cached.
                foo(1, 'bar', (1, 2, 3), range(42))  # Function not called. Cached result returned.

            - Classmethods rely on classes, which inherit from `object.__hash__`. However, classes
                are almost never garbage collected until a process exits so memoize will work as
                expected.

                class Foo:

                    @classmethod
                    @memoize
                    def bar(cls) -> Any: ...

                foo = Foo()
                foo.bar()  # Function called. Result cached.
                foo.bar()  # Function not called. Cached result returned.

                del foo  # Memo not cleared since lifetime is bound to class Foo.

                foo = Foo()
                foo.bar()  # Function not called. Cached result returned.
                foo.bar()  # Function not called. Cached result returned.

            - Long-lasting object instances that inherit from `object.__hash__`.

                class Foo:

                    @memoize
                    def bar(self) -> Any: ...

                foo = Foo()
                foo.bar()  # Function called. Result cached.
                foo.bar()  # Function not called. Cached result returned.

                del foo  # Memo is cleared since lifetime is bound to instance foo.

                foo = Foo()
                foo.bar()  # Function called. Result cached.
                foo.bar()  # Function not called. Cached result returned.

        Here are common patterns that will not behave as desired (for good reason).

            - Using ephemeral objects that inherit from `object.__hash__`. Firstly, these inputs
                will only hash equally sometimes, by accident, if their id is recycled from a
                previously deleted input. Secondly, we delete memos based on inputs that inherit
                from `object.__hash__` at the same time as that input is garbage collected, so
                generating the memo is wasted effort.

                # Inherits object.__hash__
                class Foo: ...

                @memoize
                def bar(foo: Foo) -> Any: ...

                bar(Foo())  # Memo is immediately deleted since Foo() is garbage collected.
                bar(Foo())  # Same as previous line. Memo is immediately deleted.

    Examples:

        - Body will run once for unique input 'bar' and result is cached.
            @memoize
            def foo(bar) -> Any: ...

            foo(1)  # Function actually called. Result cached.
            foo(1)  # Function not called. Cached result returned.
            foo(2)  # Function actually called. Result cached.

        - Same as above, but async.
            @memoize
            async def foo(bar) -> Any: ...

            # Concurrent calls from the same event loop are safe. Only one call is generated. The
            other nine calls in this example wait for the result.
            await asyncio.gather(*[foo(1) for _ in range(10)])

        - Classes may be memoized.
            @memoize
            Class Foo:
                def init(self, _): ...

            Foo(1)  # Instance is actually created.
            Foo(1)  # Instance not created. Cached instance returned.
            Foo(2)  # Instance is actually created.

        - Calls to foo(1), foo(bar=1), and foo(1, baz='baz') are equivalent and only cached once
            @memoize
            def foo(bar, baz='baz'): ...

        - Only 2 items are cached. Acts as an LRU.
            @memoize(size=2)
            def foo(bar) -> Any: ...

            foo(1)  # LRU cache order [foo(1)]
            foo(2)  # LRU cache order [foo(1), foo(2)]
            foo(1)  # LRU cache order [foo(2), foo(1)]
            foo(3)  # LRU cache order [foo(1), foo(3)], foo(2) is evicted to keep cache size at 2

       - Items are evicted after 1 minute.
            @memoize(duration=datetime.timedelta(minutes=1))
            def foo(bar) -> Any: ...

            foo(1)  # Function actually called. Result cached.
            foo(1)  # Function not called. Cached result returned.
            sleep(61)
            foo(1)  # Function actually called. Cached result was too old.

        - Memoize can be explicitly reset through the function's 'memoize' attribute
            @memoize
            def foo(bar) -> Any: ...

            foo(1)  # Function actually called. Result cached.
            foo(1)  # Function not called. Cached result returned.
            foo.memoize.reset()
            foo(1)  # Function actually called. Cache was emptied.

        - Current cache size can be accessed through the function's 'memoize' attribute
            @memoize
            def foo(bar) -> Any: ...

            foo(1)
            foo(2)
            len(foo.memoize)  # returns 2

        - Memoization hash keys can be generated from a non-default function:
            @memoize(keygen=lambda a, b, c: (a, b, c))
            def foo(a, b, c) -> Any: ...

        - If part of the returned key from keygen is awaitable, it will be awaited.
            async def await_something() -> Hashable: ...

            @memoize(keygen=lambda bar: (bar, await_something()))
            async def foo(bar) -> Any: ...

        - Properties can be memoized
            Class Foo:
                @property
                @memoize
                def bar(self): -> Any: ...

            a = Foo()
            a.bar  # Function actually called. Result cached.
            a.bar  # Function not called. Cached result returned.

            b = Foo() # Memoize uses 'self' parameter in hash. 'b' does not share returns with 'a'
            b.bar  # Function actually called. Result cached.
            b.bar  # Function not called. Cached result returned.

        - Be careful with eviction on methods.
            Class Foo:
                @memoize(size=1)
                def bar(self, baz): -> Any: ...

            a, b = Foo(), Foo()
            a.bar(1)  # LRU cache order [Foo.bar(a, 1)]
            b.bar(1)  # LRU cache order [Foo.bar(b, 1)], Foo.bar(a, 1) is evicted
            a.bar(1)  # Foo.bar(a, 1) is actually called and cached again.

        - The default memoize key generator can be overridden. The inputs must match the function's.
            Class Foo:
                @memoize(keygen=lambda self, a, b, c: (a, b, c))
                def bar(self, a, b, c) -> Any: ...

            a, b = Foo(), Foo()

            # Hash key will be (a, b, c)
            a.bar(1, 2, 3)  # LRU cache order [Foo.bar(a, 1, 2, 3)]

            # Hash key will again be (a, b, c)
            # Be aware, in this example the returned result comes from a.bar(...), not b.bar(...).
            b.bar(1, 2, 3)  # Function not called. Cached result returned.

        - If the memoized function is async and any part of the key is awaitable, it is awaited.
            async def morph_a(a: int) -> int: ...

            @memoize(keygen=lambda a, b, c: (morph_a(a), b, c))
            def foo(a, b, c) -> Any: ...

        - Values can persist to disk and be reloaded when memoize is initialized again.

            @memoize(db_path=Path.home() / '.memoize')
            def foo(a) -> Any: ...

            foo(1)  # Function actually called. Result cached.

            # Process is restarted. Upon restart, the state of the memoize decorator is reloaded.

            foo(1)  # Function not called. Cached result returned.
    """

    _all_decorators = WeakSet()

    @staticmethod
    def __call__(
            _decoratee: Optional[Decoratee] = None,
            *,
            db_path: Optional[Path] = None,
            duration: Optional[Union[int, float, timedelta]] = None,
            keygen: Optional[Keygen] = None,
            size: Optional[int] = None,
    ):
        if _decoratee is None:
            return partial(memoize, db_path=db_path, duration=duration, keygen=keygen, size=size)

        if inspect.isclass(_decoratee):
            assert db_path is None, 'Class memoization not allowed with db.'

            class WrappedMeta(type(_decoratee)):
                # noinspection PyMethodParameters
                @memoize(duration=duration, size=size)
                def __call__(cls, *args, **kwargs):
                    return super().__call__(*args, **kwargs)

            class Wrapped(_decoratee, metaclass=WrappedMeta):
                pass

            return type(_decoratee.__name__, (Wrapped,), {'__doc__': _decoratee.__doc__})

        db = connect(f'{db_path}') if db_path is not None else None
        duration = timedelta(seconds=duration) if isinstance(duration, (int, float)) else duration
        assert (duration is None) or (duration.total_seconds() > 0)
        assert (size is None) or (size > 0)
        fn = _decoratee
        default_kwargs: Mapping[str, Any] = {
            k: v.default for k, v in inspect.signature(fn).parameters.items()
        }

        if inspect.iscoroutinefunction(_decoratee):
            decorator_cls = _AsyncMemoize
        else:
            decorator_cls = _SyncMemoize

        # noinspection PyArgumentList
        decorator = decorator_cls(
            db=db,
            default_kwargs=default_kwargs,
            duration=duration,
            fn=fn,
            keygen=keygen,
            size=size,
        ).get_decorator()

        _Memoize._all_decorators.add(decorator)

        return wraps(_decoratee)(decorator)

    @staticmethod
    def reset_all() -> None:
        for decorator in _Memoize._all_decorators:
            decorator.memoize.reset()


memoize = _Memoize()
