from asyncio import Lock as AsyncLock
from atools.decorator_mixin import Decoratee, DecoratorMixin, Fn
from collections import deque, ChainMap, OrderedDict
from dataclasses import dataclass, field, InitVar
from datetime import timedelta
import inspect
from time import time
from threading import Lock as SyncLock
from typing import Any, Optional, Union


class _MemoZeroValue:
    pass


@dataclass
class _MemoReturnState:
    called: bool = False
    raised: bool = False
    _value: Any = _MemoZeroValue

    @property
    def value(self) -> Any:
        assert self._value is not _MemoZeroValue
        return self._value

    @value.setter
    def value(self, value: Any) -> None:
        self._value = value


@dataclass(frozen=True)
class _Memo:
    fn: Fn
    expire_time: Optional[float]
    lock: Union[AsyncLock, SyncLock] = field(init=False)
    memo_return_state: _MemoReturnState = field(init=False, default_factory=_MemoReturnState)

    def __post_init__(self) -> None:
        if inspect.iscoroutinefunction(self.fn):
            object.__setattr__(self, 'lock', AsyncLock())
        else:
            object.__setattr__(self, 'lock', SyncLock())


class _MemoizeState:
    def __init__(
            self,
            fn: Fn,
            *,
            size: Optional[int] = None,
            duration: Optional[Union[int, timedelta]] = None,
    ) -> None:
        self._fn = fn
        self._size = size
        self._duration = duration.total_seconds() if isinstance(duration, timedelta) else duration

        assert self._size is None or self._size > 0
        assert self._duration is None or self._duration > 0

        if self._duration is None:
            self._expire_order = None
        else:
            self._expire_order = OrderedDict()
        self._memos: OrderedDict = OrderedDict()
        self._default_kwargs: OrderedDict = OrderedDict([
            (k, v.default) for k, v in inspect.signature(self._fn).parameters.items()
        ])

    def __len__(self) -> int:
        return len(self._memos)

    def reset(self) -> None:
        self._memos = OrderedDict()
        self._expire_order = deque() if self._expire_order is not None else None

    def make_key(self, *args, **kwargs) -> int:
        """Returns all params (args, kwargs, and missing default kwargs) for function as kwargs."""
        args_as_kwargs = {}
        for k, v in zip(self._default_kwargs, args):
            args_as_kwargs[k] = v

        return hash(tuple(ChainMap(args_as_kwargs, kwargs, self._default_kwargs).values()))

    def get_memo(self, key: int) -> _Memo:
        try:
            memo = self._memos[key] = self._memos.pop(key)
            if self._duration is not None and memo.expire_time < time():
                self._expire_order.pop(key)
                raise ValueError('value expired')
        except (KeyError, ValueError):
            if self._duration is None:
                expire_time = None
            else:
                expire_time = time() + self._duration
                self._expire_order[key] = ...

            memo = self._memos[key] = _Memo(self._fn, expire_time=expire_time)

        return memo

    def expire_one_memo(self) -> None:
        if self._expire_order is not None and \
                len(self._expire_order) > 0 and \
                self._memos[next(iter(self._expire_order))].expire_time < time():
            self._memos.pop(self._expire_order.popitem(last=False)[0])
        elif self._size is not None and self._size < len(self._memos):
            self._memos.popitem(last=False)


_all_decorators = set()


@dataclass(frozen=True)
class _MemoizeAsync:
    fn: InitVar[Fn]
    size: InitVar[Optional[int]] = None
    duration: InitVar[Optional[Union[int, timedelta]]] = None
    _state: _MemoizeState = field(init=False)

    def __post_init__(
            self, fn: Fn, size: Optional[int], duration: Optional[Union[int, timedelta]]
    ) -> None:
        object.__setattr__(self, '_state', _MemoizeState(fn=fn, size=size, duration=duration))
        _all_decorators.add(self)

    async def __call__(self, *args, **kwargs) -> Any:
        key = self._state.make_key(*args, **kwargs)

        memo = self._state.get_memo(key)

        self._state.expire_one_memo()

        async with memo.lock:
            if not memo.memo_return_state.called:
                memo.memo_return_state.called = True
                try:
                    memo.memo_return_state.value = await memo.fn(*args, **kwargs)
                except Exception as e:
                    memo.memo_return_state.raised = True
                    memo.memo_return_state.value = e

            if memo.memo_return_state.raised:
                raise memo.memo_return_state.value
            else:
                return memo.memo_return_state.value

    def __len__(self) -> int:
        return len(self._state)

    def reset(self) -> None:
        self._state.reset()


_memoize_async = type('memoize', (_MemoizeAsync,), {})


@dataclass(frozen=True)
class _MemoizeSync:
    fn: InitVar[Fn]
    size: InitVar[Optional[int]] = None
    duration: InitVar[Optional[Union[int, timedelta]]] = None
    _state: _MemoizeState = field(init=False)
    _sync_lock: SyncLock = field(init=False, default_factory=SyncLock)

    def __post_init__(
            self, fn: Fn, size: Optional[int], duration: Optional[Union[int, timedelta]]
    ) -> None:
        object.__setattr__(self, '_state', _MemoizeState(fn=fn, size=size, duration=duration))
        _all_decorators.add(self)

    def __call__(self, *args, **kwargs) -> Any:
        key = self._state.make_key(*args, **kwargs)

        with self._sync_lock:
            memo = self._state.get_memo(key)

        self._state.expire_one_memo()

        with memo.lock:
            if not memo.memo_return_state.called:
                memo.memo_return_state.called = True
                try:
                    memo.memo_return_state.value = memo.fn(*args, **kwargs)
                except Exception as e:
                    memo.memo_return_state.raised = True
                    memo.memo_return_state.value = e

            if memo.memo_return_state.raised:
                raise memo.memo_return_state.value
            else:
                return memo.memo_return_state.value

    def __len__(self) -> int:
        return len(self._state)

    def reset(self) -> None:
        with self._sync_lock:
            self._state.reset()


_memoize_sync = type('memoize', (_MemoizeSync,), {})


class _Memoize:
    """Decorates a function call and caches return value for given inputs.

    If 'size' is provided, memoize will only retain up to 'size' return values.

    If 'expire' is provided, memoize will only retain return values for up to 'expire' duration.

    Examples:

        - Body will run once for unique input 'bar' and result is cached.
            @memoize
            def foo(bar) -> Any: ...

            foo(1)  # Function actually called. Result cached.
            foo(1)  # Function not called. Previously-cached result returned.
            foo(2)  # Function actually called. Result cached.

        - Same as above, but async.
            @memoize
            async def foo(bar) -> Any: ...

            # Concurrent calls from the same thread are safe. Only one call is generated. The
            other nine calls in this example wait for the result.
            await asyncio.gather(*[foo(1) for _ in range(10)])

        - Classes may be memoized.
            @memoize
            Class Foo:
                def init(self, _): ...

            Foo(1)  # Instance is actually created.
            Foo(1)  # Instance not created. Previously-cached instance returned.
            Foo(2)  # Instance is actually created.

        - Calls to foo(1), foo(bar=1), and foo(1, baz='baz') are equivalent and only cached once
            @memoize
            def foo(bar, baz='baz'): ...

        - Only 10 items are cached. Acts as an LRU.
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
            foo(1)  # Function not called. Previously-cached result returned.
            sleep(61)
            foo(1)  # Function actually called. Previously-cached result was too old.

        - Memoize can be explicitly reset through the function's 'memoize' attribute
            @memoize
            def foo(bar) -> Any: ...

            foo(1)  # Function actually called. Result cached.
            foo(1)  # Function not called. Previously-cached result returned.
            foo.memoize.reset()
            foo(1)  # Function actually called. Cache was emptied.

        - Current cache size can be accessed through the function's 'memoize' attribute
            @memoize
            def foo(bar) -> Any: ...

            foo(1)
            foo(2)
            len(foo.memoize)  # returns 2

        - Properties can be memoized
            Class Foo:
                @property
                @memoize
                def bar(self, baz): -> Any: ...

            a = Foo()
            a.bar  # Function actually called. Result cached.
            a.bar  # Function not called. Previously-cached result returned.

            b = Foo() # Memoize uses 'self' parameter in hash. 'b' does not share returns with 'a'
            b.bar  # Function actually called. Result cached.
            b.bar  # Function not called. Previously-cached result returned.

        - Be careful with eviction on methods.
            Class Foo:
                @memoize(size=1)
                def foo(self): -> Any: ...

            a, b = Foo(), Foo()
            a.bar(1)  # LRU cache order [Foo.bar(a)]
            b.bar(1)  # LRU cache order [Foo.bar(b)], Foo.bar(a) is evicted
            a.bar(1)  # Foo.bar(a, 1) is actually called cached and again.
    """

    _all_decorators = set()

    def __new__(
            cls,
            decoratee: Decoratee,
            *,
            size: Optional[int] = None,
            duration: Optional[Union[int, timedelta]] = None,
    ):
        if inspect.iscoroutinefunction(decoratee):
            return _memoize_async(decoratee, size=size, duration=duration)
        elif not inspect.isclass(decoratee):
            return _memoize_sync(decoratee, size=size, duration=duration)
        elif inspect.isclass(decoratee):
            class WrappedMeta(type(decoratee)):
                # noinspection PyMethodParameters
                @memoize
                def __call__(cls, *args, **kwargs):
                    return super().__call__(*args, **kwargs)

            class Wrapped(decoratee, metaclass=WrappedMeta):
                pass

            return type(decoratee.__name__, (Wrapped,), {'__doc__': decoratee.__doc__})

    @staticmethod
    def reset_all() -> None:
        for decorator in _all_decorators:
            decorator.reset()


memoize = type('memoize', (DecoratorMixin, _Memoize), {})
