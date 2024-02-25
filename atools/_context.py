from __future__ import annotations
import abc
import contextlib
import dataclasses
import functools
import inspect
import typing


@typing.final
class State[** Params, Return](abc.ABC):

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class Base:
        args: Params.args = ...
        kwargs: Params.kwargs = ...
        return_: Return = ...

    class Async(Base):
        ...

    class Multi(Base):
        ...

    class Top(Async, Multi):
        ...


@typing.final
class Context[** Params, Return](abc.ABC):

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class Base:
        states: list[State[Params, Return].Base] = dataclasses.field(default_factory=list)
        decoratee: Decoratee[Params, Return].Base

    class Async(Base):
        ...

    class Multi(Base):
        ...

    class Top(Async, Multi):
        ...


@typing.final
class Decoratee[** Params, Return](abc.ABC):
    type Async = typing.Callable[Params, typing.Awaitable[Return]]
    type Multi = typing.Callable[Params, Return]
    type Top = Decoratee[Params, Return].Async | Decoratee[Params, Return].Multi
    ...


@typing.final
class Decorated[** Params, Return](abc.ABC):

    @dataclasses.dataclass(kw_only=True)
    class Base:
        context: Context[Params, Return].Base

    class Async(Base):
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

    class Multi(Base):
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

    class Top(Async, Multi):
        ...


@typing.final
class Decorator[** Params, Return](abc.ABC):

    @dataclasses.dataclass(frozen=True)
    class Base:
        ...

    class Async(Base):
        def __call__(self, decoratee: Decoratee[Params, Return].Async, /) -> Decorated[Params, Return].Async:
            if not isinstance(decoratee, Decorated[Params, Return].Async):
                decoratee = inspect.markcoroutinefunction(Decorated[Params, Return].Async(
                    context=Context[Params, Return].Async(decoratee=decoratee)
                ))

            decorated: Decorated[Params, Return].Top = decoratee

            return decorated

    class Multi(Base):
        def __call__(self, decoratee: Decoratee[Params, Return].Multi, /) -> Decorated[Params, Return].Multi:
            if not isinstance(decoratee, Decorated[Params, Return].Multi):
                decoratee = functools.wraps(decoratee)(inspect.markcoroutinefunction(Decorated[Params, Return].Multi(
                    context=Context[Params, Return].Multi(decoratee=decoratee)
                )))

            decorated: Decorated[Params, Return].Top = decoratee

            return decorated

    class Top(Async, Multi):

        @typing.overload
        def __call__(self, decoratee: Decoratee[Params, Return].Async, /) -> Decorated[Params, Return].Async: ...

        @typing.overload
        def __call__(self, decoratee: Decoratee[Params, Return].Multi, /) -> Decorated[Params, Return].Multi: ...

        def __call__(self, decoratee: Decoratee[Params, Return].Top, /) -> Decorated[Params, Return].Top:
            if inspect.iscoroutinefunction(decoratee):
                return Decorator[Params, Return].Async.__call__(self, decoratee)
            else:
                return Decorator[Params, Return].Multi.__call__(self, decoratee)
