from __future__ import annotations
import abc
import contextlib
import dataclasses
import functools
import inspect
import typing

from ._decoratee import Decorated as Decoratee


@typing.final
class State(abc.ABC):

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class Base[** Params, Return](abc.ABC):
        args: Params.args = ...
        kwargs: Params.kwargs = ...
        return_: Return = ...

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class Async[** Params, Return](Base[Params, Return], contextlib.AbstractAsyncContextManager, abc.ABC):
        ...

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class Multi[** Params, Return](Base[Params, Return], contextlib.AbstractContextManager, abc.ABC):
        ...

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class Top[** Params, Return](Async[Params, Return], Multi[Params, Return], abc.ABC):
        ...


@typing.final
class Decoration(abc.ABC):

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class Base[** Params, Return]:
        decoratee: Decoratee.Top[Params, Return]
        states: list[State.Top[Params, Return]] = dataclasses.field(default_factory=list)

    class Async[** Params, Return](Base[Params, Return]):
        ...

    class Multi[** Params, Return](Base[Params, Return]):
        ...

    class Top[** Params, Return](Async[Params, Return], Multi[Params, Return]):
        ...


Context = Decoration


@typing.final
class Decorated(abc.ABC):

    @dataclasses.dataclass(kw_only=True)
    class Base[** Params, Return]:
        context: Context.Top[Params, Return]

    class Async[** Params, Return](Base[Params, Return]):
        async def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return:
            async with contextlib.AsyncExitStack() as stack:
                states = [
                    await stack.enter_async_context(dataclasses.replace(state, args=args, kwargs=kwargs))
                    for state in reversed(self.context.states)
                ]

                return_ = await self.context.decoratee(*args, **kwargs)

                for state in reversed(states):
                    await state(return_)

            return return_

    class Multi[** Params, Return](Base[Params, Return]):
        def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return:
            with contextlib.ExitStack() as stack:
                states = [
                    stack.enter_context(dataclasses.replace(state, args=args, kwargs=kwargs))
                    for state in reversed(self.context.states)
                ]

                return_ = self.context.decoratee(*args, **kwargs)

                for state in reversed(states):
                    state(return_)

            return return_

    type Top[** Params, Return] = Decorated.Async[Params, Return] | Decorated.Multi[Params, Return]
    ...


@typing.final
class Decorator(abc.ABC):

    @dataclasses.dataclass(frozen=True)
    class Base[** Params, Return]:
        ...

    class Async[** Params, Return](Base[Params, Return]):
        def __call__(self, decoratee: Decoratee.Async[Params, Return], /) -> Decorated.Async[Params, Return]:
            if not isinstance(decoratee, Decorated.Async):
                decoratee = inspect.markcoroutinefunction(Decorated.Async[Params, Return](
                    context=Context.Async[Params, Return](decoratee=decoratee)
                ))

            decorated: Decorated.Top[Params, Return] = decoratee

            return decorated

    class Multi[** Params, Return](Base[Params, Return]):
        def __call__(self, decoratee: Decoratee.Multi[Params, Return], /) -> Decorated.Multi[Params, Return]:
            if not isinstance(decoratee, Decorated.Multi):
                decoratee = functools.wraps(decoratee)(inspect.markcoroutinefunction(Decorated.Multi[Params, Return](
                    context=Context.Multi[Params, Return](decoratee=decoratee)
                )))

            decorated: Decorated.Top[Params, Return] = decoratee

            return decorated

    class Top[** Params, Return](Async[Params, Return], Multi[Params, Return]):

        @typing.overload
        def __call__(self, decoratee: Decoratee.Async[Params, Return], /) -> Decorated.Async[Params, Return]: ...

        @typing.overload
        def __call__(self, decoratee: Decoratee.Multi[Params, Return], /) -> Decorated.Multi[Params, Return]: ...

        def __call__(self, decoratee: Decoratee.Top[Params, Return], /) -> Decorated.Top[Params, Return]:
            if inspect.iscoroutinefunction(decoratee):
                return Decorator.Async.__call__(self, decoratee)
            else:
                return Decorator.Multi.__call__(self, decoratee)
