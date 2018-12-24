from asyncio import iscoroutine, Event
from atools.decorator_mixin import DecoratorMixin, Fn
from collections import ChainMap, OrderedDict
from inspect import signature
from typing import Any, Optional


class _Memo:
    _sync_called: bool = False
    _sync_return: Any
    _sync_raise: bool = False
    _async_called: bool = False
    _async_return: Any
    _async_raise: bool = False
    _event: Optional[Event] = None

    def __init__(self, fn: Fn):
        self._fn = fn

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

    def __init__(self, fn, *, size: Optional[int] = None) -> None:
        self._fn = fn
        self._size = size
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
            self._memos[key] = self._memos.pop(key)
        except KeyError:
            self._memos[key] = _Memo(self._fn)

        if self._size is not None and self._size < len(self._memos):
            self._memos.popitem(last=False)

        return self._memos[key](**kwargs)


memoize = type('Memoize', (DecoratorMixin, _Memoize), {})
