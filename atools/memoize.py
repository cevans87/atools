from atools.decorator_mixin import DecoratorMixin
from collections import ChainMap, OrderedDict
from inspect import signature
from typing import Any


class _Memoize:

    def __init__(self, fn) -> None:
        self._fn = fn
        self._memoize: OrderedDict = OrderedDict()
        self._default_kwargs: OrderedDict = OrderedDict([
            (k, v.default) for k, v in signature(self._fn).parameters.items()
        ])

    def __call__(self, *args, **kwargs) -> Any:
        for k, v in zip(self._default_kwargs, args):
            kwargs[k] = v
        kwargs = ChainMap(kwargs, self._default_kwargs)

        key = tuple(kwargs.values())

        try:
            self._memoize[key] = self._memoize.pop(key)
        except KeyError:
            self._memoize[key] = self._fn(**kwargs)

        return self._memoize[key]


memoize = type('Memoize', (DecoratorMixin, _Memoize), {})
