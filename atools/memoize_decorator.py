from asyncio import iscoroutine, Event
from atools.decorator_mixin import DecoratorMixin, Fn
from atools.util import seconds
from collections import deque, ChainMap, OrderedDict
from inspect import signature
from time import time
from typing import Any, Optional


class _Memo:
    _sync_called: bool = False
    _sync_return: Any
    _sync_raise: bool = False
    _async_called: bool = False
    _async_return: Any
    _async_raise: bool = False
    _event: Optional[Event] = None

    def __init__(self, fn: Fn, expire_time: Optional[float] = None) -> None:
        self._fn = fn
        self.expire_time = expire_time

    def __call__(self, **kwargs):
        if not self._sync_called:
            self._sync_called = True
            try:
                self._sync_return = self._fn(**kwargs)
            except Exception as e:
                self._sync_raise = True
                self._sync_return = e

        if iscoroutine(self._sync_return):
            return self.__async_unwrap()
        elif self._sync_raise:
            raise self._sync_return
        else:
            return self._sync_return

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

    def __init__(
            self,
            fn,
            *,
            size: Optional[int] = None,
            expire: Optional[str] = None
    ) -> None:

        self._fn = fn
        self._size = size
        self._expire_seconds = seconds(expire) if expire is not None else None

        if self._expire_seconds is None:
            self._expire_order = None
        else:
            self._expire_order = deque()
        self._memos: OrderedDict = OrderedDict()
        self._default_kwargs: OrderedDict = OrderedDict([
            (k, v.default) for k, v in signature(self._fn).parameters.items()
        ])

    def __call__(self, *args, **kwargs) -> Any:
        for k, v in zip(self._default_kwargs, args):
            kwargs[k] = v
        kwargs = ChainMap(kwargs, self._default_kwargs)

        key = tuple(kwargs.values())

        try:
            value = self._memos.pop(key)
            if self._expire_seconds is not None and value.expire_time < time():
                raise ValueError('value expired')
        except (KeyError, ValueError):
            if self._expire_seconds is None:
                expire_time = None
            else:
                expire_time = time() + self._expire_seconds
                self._expire_order.append(key)
            self._memos[key] = _Memo(self._fn, expire_time=expire_time)
        else:
            self._memos[key] = value

        if self._expire_order is not None and \
                self._memos[self._expire_order[0]].expire_time < time():
            self._memos.pop(self._expire_order.popleft())
        elif self._size is not None and self._size < len(self._memos):
            self._memos.popitem(last=False)

        return self._memos[key](**kwargs)


memoize = type('Memoize', (DecoratorMixin, _Memoize), {})
