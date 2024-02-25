from __future__ import annotations
import dataclasses
import inspect
import typing

from . import _async as Async, _base as Base, _sync as Sync  # noqa


type Context[** Params, Return] = Async.Context[Params, Return] | Sync.Context[Params, Return]
type Decoratee[** Params, Return] = Async.Decoratee[Params, Return] | Sync.Decoratee[Params, Return]
type Decoration[** Params, Return] = Async.Decoration[Params, Return] | Sync.Decoration[Params, Return]
type Decorated[** Params, Return] = Async.Decorated[Params, Return] | Sync.Decorated[Params, Return]


@dataclasses.dataclass(frozen=True)
class Decorator(Base.Decorator):

    @typing.overload
    def __call__[** Params, Return](
        self, decoratee: Async.Decoratee[Params, Return], /
    ) -> Async.Decorated[Params, Return]: ...

    @typing.overload
    def __call__[** Params, Return](
        self, decoratee: Sync.Decoratee[Params, Return], /
    ) -> Sync.Decorated[Params, Return]: ...

    def __call__[** Params, Return](self, decoratee: Decoratee[Params, Return], /) -> Decorated[Params, Return]:
        if inspect.iscoroutinefunction(decoratee):
            return Async.Decorator(self._prefix, self._suffix)(decoratee)
        return Sync.Decorator(self._prefix, self._suffix)(decoratee)
