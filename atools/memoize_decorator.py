from asyncio import Lock as AsyncLock
from collections import ChainMap, OrderedDict
from dataclasses import dataclass, field
from datetime import timedelta
from functools import partial, wraps
import inspect
from time import time
from threading import Lock as SyncLock
from typing import Any, Callable, Mapping, Optional, Type, Union


Decoratee = Union[Callable, Type]


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
class _MemoBase:
    fn: Callable
    expire_time: Optional[float]
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
    fn: Callable
    size: Optional[int]
    duration: Optional[timedelta]
    default_kwargs: Mapping[str, Any]
    
    expire_order: OrderedDict = field(init=False, default_factory=OrderedDict, hash=False)
    memos: OrderedDict = field(init=False, default_factory=OrderedDict, hash=False)

    def __len__(self) -> int:
        return len(self.memos)
    
    def make_key(self, *args, **kwargs) -> int:
        """Returns all params (args, kwargs, and missing default kwargs) for function as kwargs."""
        args_as_kwargs = {}
        for k, v in zip(self.default_kwargs, args):
            args_as_kwargs[k] = v

        return hash(tuple(ChainMap(args_as_kwargs, kwargs, self.default_kwargs).values()))
    
    def get_memo(self, key: int) -> _Memo:
        try:
            memo = self.memos[key] = self.memos.pop(key)
            if self.duration is not None and memo.expire_time < time():
                self.expire_order.pop(key)
                raise ValueError('value expired')
        except (KeyError, ValueError):
            if self.duration is None:
                expire_time = None
            else:
                expire_time = time() + self.duration.total_seconds()
                # The value has no significance. We're using the dict entirely for ordering keys.
                self.expire_order[key] = ...

            memo = self.memos[key] = self.make_memo(self.fn, expire_time=expire_time)

        return memo

    def expire_one_memo(self) -> None:
        if self.expire_order is not None and \
                len(self.expire_order) > 0 and \
                self.memos[next(iter(self.expire_order))].expire_time < time():
            self.memos.pop(self.expire_order.popitem(last=False)[0])
        elif self.size is not None and self.size < len(self.memos):
            self.memos.popitem(last=False)

    def make_memo(self, fn, expire_time: Optional[float]) -> _Memo:  # pragma: no cover
        raise NotImplemented
    
    def reset(self) -> None:
        object.__setattr__(self, 'expire_order', OrderedDict())
        object.__setattr__(self, 'memos', OrderedDict())


@dataclass(frozen=True)
class _AsyncMemoize(_MemoizeBase):
    
    def get_decorator(self) -> Callable:
        async def decorator(*args, **kwargs) -> Any:
            key = self.make_key(*args, **kwargs)

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

                if memo.memo_return_state.raised:
                    raise memo.memo_return_state.value
                else:
                    return memo.memo_return_state.value

        decorator.memoize = self

        return decorator

    def make_memo(self, fn, expire_time: Optional[float]) -> _AsyncMemo:
        return _AsyncMemo(fn=fn, expire_time=expire_time)
    

@dataclass(frozen=True)
class _SyncMemoize(_MemoizeBase):

    _sync_lock: SyncLock = field(init=False, default_factory=lambda: SyncLock())
    
    def get_decorator(self) -> Callable:
        def decorator(*args, **kwargs):
            key = self.make_key(*args, **kwargs)

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

                if memo.memo_return_state.raised:
                    raise memo.memo_return_state.value
                else:
                    return memo.memo_return_state.value
                
        decorator.memoize = self
                
        return decorator

    def make_memo(self, fn, expire_time: Optional[float]) -> _SyncMemo:
        return _SyncMemo(fn=fn, expire_time=expire_time)

    def reset(self) -> None:
        with self._sync_lock:
            super().reset()


_Memoize = Union[_AsyncMemoize, _SyncMemoize]

_all_decorators = set()


def memoize(
    _decoratee: Optional[Decoratee] = None,
    *,
    size: Optional[int] = None,
    duration: Optional[Union[int, float, timedelta]] = None
):
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
    if _decoratee is None:
        return partial(memoize, size=size, duration=duration)
    
    if inspect.isclass(_decoratee):
        class WrappedMeta(type(_decoratee)):
            # noinspection PyMethodParameters
            @memoize(size=size, duration=duration)
            def __call__(cls, *args, **kwargs):
                return super().__call__(*args, **kwargs)

        class Wrapped(_decoratee, metaclass=WrappedMeta):
            pass

        return type(_decoratee.__name__, (Wrapped,), {'__doc__': _decoratee.__doc__})

    duration = timedelta(seconds=duration) if isinstance(duration, (int, float)) else duration
    assert (duration is None) or (duration.total_seconds() > 0)
    assert (size is None) or (size > 0)
    fn = _decoratee
    default_kwargs: Mapping[str, Any] = {
        k: v.default for k, v in inspect.signature(fn).parameters.items()
    }

    if inspect.iscoroutinefunction(_decoratee):
        decorator = _AsyncMemoize(
            fn=fn, size=size, duration=duration, default_kwargs=default_kwargs
        ).get_decorator()
    else:
        decorator = _SyncMemoize(
            fn=fn, size=size, duration=duration, default_kwargs=default_kwargs
        ).get_decorator()

    _all_decorators.add(decorator)
    
    return wraps(_decoratee)(decorator)


def reset_all() -> None:
    for decorator in _all_decorators:
        decorator.memoize.reset()


memoize.reset_all = reset_all
