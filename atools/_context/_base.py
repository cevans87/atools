import dataclasses as _dataclasses

from .. import _key


@_dataclasses.dataclass(frozen=True, kw_only=True)
class Context[_Decoratee, ** Params]:
    args: Params.args = ...
    kwargs: Params.kwargs = ...
    decoratee: _Decoratee


@_dataclasses.dataclass(frozen=True, kw_only=True)
class Decoration[_Context: Context, _Decoratee, ** Params, Return]:
    contexts: list[_Context] = _dataclasses.field(default_factory=list)
    decoratee: _Decoratee


@_dataclasses.dataclass(kw_only=True)
class Decorated[_Decoration: Decoration](_key.Base.Decorated):
    context: _Decoration


@_dataclasses.dataclass(frozen=True)
class Decorator(_key.Base.Decorator):
    ...
