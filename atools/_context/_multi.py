import abc
import contextlib
import dataclasses
import functools
import typing

from . import _base


type Decoratee[** Params, Return] = typing.Callable[Params, Return]


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](
    contextlib.AbstractContextManager,
    _base.Context[Decoratee[Params, Return], Params],
    abc.ABC,
):

    @abc.abstractmethod
    def __call__(self, return_: Return) -> None: ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class Decoration[** Params, Return](
    _base.Decoration[Context[Params, Return], Decoratee[Params, Return], Params, Return]
):
    ...


@dataclasses.dataclass(kw_only=True)
class DecoratedData[** Params, Return](_base.Decorated[Decoration[Params, Return]]):
    ...


@dataclasses.dataclass(kw_only=True)
class Decorated[** Params, Return](DecoratedData[Params, Return]):
    def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return:
        with contextlib.ExitStack() as stack:
            contexts = [stack.enter_context(
                dataclasses.replace(context, args=args, kwargs=kwargs, decoratee=self.context.decoratee)
            ) for context in reversed(self.context.contexts)]

            return_ = self.context.decoratee(*args, **kwargs)

            for context in reversed(contexts):
                context(return_)

        return return_


@dataclasses.dataclass(frozen=True)
class Decorator(_base.Decorator):
    def __call__[** Params, Return](
        self, decoratee: Decoratee[Params, Return], /
    ) -> Decorated[Params, Return]:
        decoratee: Decoratee[Params, Return]
        if isinstance(getattr(decoratee, 'context', None), Decoration):
            decoratee: Decorated[Params, Return]
            decorated = decoratee
        else:
            decorated: Decorated[Params, Return] = functools.wraps(decoratee)(
                Decorated[Params, Return](context=Decoration[Params, Return](decoratee=decoratee))
            )

        return decorated
