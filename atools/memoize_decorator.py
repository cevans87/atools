from asyncio import Event
from atools.decorator_mixin import DecoratorMixin, Fn
from atools.util import duration
from collections import deque, ChainMap, OrderedDict
import inspect
from time import time
from threading import Lock
from typing import Any, Optional, Tuple, Union


class _Memo:
    _sync_called: bool = False
    _sync_return: Any = None
    _sync_raise: bool = False
    _async_called: bool = False
    _async_return: Any = None
    _async_raise: bool = False
    _event: Optional[Event] = None

    def __init__(
            self, fn: Fn, expire_time: Optional[float] = None, thread_safe: bool = False
    ) -> None:
        self._fn = fn
        self.expire_time = expire_time
        self._lock: Optional[Lock] = Lock() if thread_safe is True else None

    def __call__(self, *args, **kwargs):
        with self:
            if not self._sync_called:
                self._sync_called = True
                try:
                    self._sync_return = self._fn(*args, **kwargs)
                except Exception as e:
                    self._sync_raise = True
                    self._sync_return = e

        if inspect.iscoroutine(self._sync_return):
            return self.__async_unwrap()
        elif self._sync_raise:
            raise self._sync_return
        else:
            return self._sync_return

    def __enter__(self) -> None:
        if self._lock is not None:
            self._lock.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._lock is not None:
            self._lock.release()

    async def __async_unwrap(self):
        if self._async_called:
            await self._event.wait()
        else:
            self._async_called = True
            self._event = Event()
            try:
                self._async_return = await self._sync_return
            except Exception as e:
                self._async_raise = True
                self._async_return = e
            self._event.set()

        if self._async_raise:
            raise self._async_return
        else:
            return self._async_return


class _Memoize:
    """Decorates a function call and caches return value for given inputs.

    If 'size' is provided, memoize will only retain up to 'size' return values.

    If 'expire' is provided, memoize will only retain return values for up to 'expire' duration.
      'expire' duration is given as a number of seconds or a string such as '10s', '1m', or
      '1d1h1m1s' where days, hours, minutes, and seconds are represented by 'd', 'h', 'm', and
      's' respectively.

    If 'pass_unhashable' is True, memoize will not remember calls that are made with parameters
      that cannot be hashed instead of raising an exception.

    if 'thread_safe' is True, the decorator is guaranteed to be thread safe.

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
            @memoize(expire='1m')
            def foo(bar) -> Any: ...

            foo(1)  # Function actually called. Result cached.
            foo(1)  # Function not called. Previously-cached result returned.
            sleep(61)
            foo(1)  # Function actually called. Previously-cached result was too old.

        - Thread safety is not enabled by default. It must be explicitly enabled.
            @memoize(thread_safe=True)
            def foo(bar) -> Any: ...

            # Concurrent calls from multiple threads are safe. Only one call is generated. The
            # other nine calls in this example wait for the result.
            concurrent.futures.Executor.map(foo, [1] * 10)

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

        - Be careful with eviction on instance methods.
            Class Foo:
                @memoize(size=1)
                def foo(self): -> Any: ...

            a, b = Foo(), Foo()
            a.bar(1)  # LRU cache order [Foo.bar(a)]
            b.bar(1)  # LRU cache order [Foo.bar(b)], Foo.bar(a) is evicted
            a.bar(1)  # Foo.bar(a, 1) is actually called cached and again.
    """

    def __init__(
            self,
            fn: Fn,
            *,
            size: Optional[int] = None,
            expire: Optional[Union[int, str]] = None,
            pass_unhashable: bool = False,
            thread_safe: bool = False,
    ) -> None:

        self._fn = fn
        self._size = size
        self._expire_seconds = duration(expire) if expire is not None else None
        self._pass_unhashable = pass_unhashable
        self._lock = Lock() if thread_safe else None

        assert self._size is None or self._size > 0
        assert self._expire_seconds is None or self._expire_seconds > 0

        if self._expire_seconds is None:
            self._expire_order = None
        else:
            self._expire_order = OrderedDict()
        self._memos: OrderedDict = OrderedDict()
        self._default_kwargs: OrderedDict = OrderedDict([
            (k, v.default) for k, v in inspect.signature(self._fn).parameters.items()
        ])

    def __call__(self, *args, **kwargs) -> Any:
        key = self._make_key(*args, **kwargs)

        with self:
            memo = self._get_memo(key)
            self._expire_one_memo()

        return memo(*args, **kwargs)

    def __enter__(self) -> None:
        if self._lock is not None:
            self._lock.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._lock is not None:
            self._lock.release()

    def __len__(self) -> int:
        with self:
            return len(self._memos)

    def reset(self) -> None:
        with self:
            self._memos = OrderedDict()
            self._expire_order = deque() if self._expire_order is not None else None

    def _make_key(self, *args, **kwargs) -> Tuple:
        """Returns all params (args, kwargs, and missing default kwargs) for function as kwargs."""
        args_as_kwargs = {}
        for k, v in zip(self._default_kwargs, args):
            args_as_kwargs[k] = v

        return tuple(ChainMap(args_as_kwargs, kwargs, self._default_kwargs).values())

    def _get_memo(self, key) -> _Memo:
        try:
            memo = self._memos[key] = self._memos.pop(key)
            if self._expire_seconds is not None and memo.expire_time < time():
                self._expire_order.pop(key)
                raise ValueError('value expired')
        except TypeError:
            if not self._pass_unhashable:
                raise
            memo = _Memo(self._fn)
        except (KeyError, ValueError):
            if self._expire_seconds is None:
                expire_time = None
            else:
                expire_time = time() + self._expire_seconds
                self._expire_order[key] = ...
            memo = self._memos[key] = _Memo(
                self._fn, expire_time=expire_time, thread_safe=self._lock is not None)

        return memo

    def _expire_one_memo(self) -> None:
        if self._expire_order is not None and \
                len(self._expire_order) > 0 and \
                self._memos[next(iter(self._expire_order))].expire_time < time():
            self._memos.pop(self._expire_order.popitem(last=False)[0])
        elif self._size is not None and self._size < len(self._memos):
            self._memos.popitem(last=False)


memoize = type('memoize', (DecoratorMixin, _Memoize), {})
