import dataclasses

from .. import bofdsfdfsa


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[_Decoratee, ** Params]:
    args: Params.args = ...
    kwargs: Params.kwargs = ...
    decoratee: _Decoratee


class Decorated


@dataclasses.dataclass(frozen=True, kw_only=True)
class Decoration[_Context: Context, _Decoratee, ** Params, Return]:
    contexts: list[_Context] = dataclasses.field(default_factory=list)
    decoratee: _Decoratee


@dataclasses.dataclass(kw_only=True)
class Decorated[_Decoration: Decoration](bofdsfdfsa.Base.Decorated):
    context: _Decoration


@dataclasses.dataclass(frozen=True)
class Decorator(bofdsfdfsa.Base.Decorator):
    ...
