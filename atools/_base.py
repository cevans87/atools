from __future__ import annotations
import abc
import functools
import contextlib
import dataclasses
import inspect
import types
import typing


@typing.runtime_checkable
class Decoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, typing.Awaitable[Return] | Return]


@typing.runtime_checkable
class _Async[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, typing.Awaitable[Return]]


@typing.runtime_checkable
class _Multi[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, Return]


# Monkey patching circumvents having these attributes as isinstance requirements for `Decoratee`.
Decoratee.Async = _Async
Decoratee.Multi = _Multi


class Decoration[** Params, Return](abc.ABC):

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class Base[** Params, Return]:
        decoratee: Decoratee[Params, Return]
        args: Params.args = ...
        kwargs: Params.kwargs = ...
        return_: Return = ...

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class Async[** Params, Return](Base[Params, Return], abc.ABC):
        __call__: typing.Callable[[Return], typing.Awaitable[Return]] = ...

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None:
            return None

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class Multi[** Params, Return](Base[Params, Return], abc.ABC):
        __call__: typing.Callable[[Return], Return] = ...

        def __enter__(self):
            return self

        def __exit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None:
            return None

    type Top[** Params, Return] = Decoration.Async[Params, Return] | Decoration.Multi[Params, Return]

    @classmethod
    @typing.overload
    def of_decoratee(cls, decoratee: Decoratee.Async[Params, Return], /) -> Decoration.Async[Params, Return]: ...

    @classmethod
    @typing.overload
    def of_decoratee(cls, decoratee: Decoratee.Multi[Params, Return], /) -> Decoration.Multi[Params, Return]: ...

    @classmethod
    @typing.final
    def of_decoratee(cls, decoratee: Decoratee[Params, Return], /) -> Decoration[Params, Return]:
        mixin = cls.Async if inspect.iscoroutinefunction(decoratee) else cls.Multi
        print(locals())

        return type(f'{mixin.__name__}{cls.__name__}', (mixin, cls), dict(mixin.__dict__))(decoratee)


class Decorated[** Params, Return](abc.ABC):

    @dataclasses.dataclass(kw_only=True)
    class Base[** Params, Return](abc.ABC):
        decoratee: Decoratee[Params, Return]
        decorations: tuple[Decoration[Params, Return], ...] = dataclasses.field(default_factory=tuple)

    @dataclasses.dataclass(kw_only=True)
    class Async[** Params, Return](Base[Params, Return]):
        decoratee: Decoratee.Async[Params, Return]
        decorations: tuple[Decoration.Async[Params, Return], ...] = dataclasses.field(default_factory=tuple)

        async def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return:
            async with contextlib.AsyncExitStack() as stack:
                decorations = [
                    await stack.enter_async_context(dataclasses.replace(decoration, args=args, kwargs=kwargs))
                    for decoration in reversed(self.decorations)
                ]

                return_ = await self.decoratee(*args, **kwargs)

                for decoration in reversed(decorations):
                    await decoration(return_)

            return return_

    @dataclasses.dataclass(kw_only=True)
    class Multi[** Params, Return](Base[Params, Return]):
        decoratee: Decoratee.Multi[Params, Return]
        decorations: tuple[Decoration.Multi[Params, Return], ...] = dataclasses.field(default_factory=tuple)

        def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return:
            with contextlib.ExitStack() as stack:
                decorations = [
                    stack.enter_context(dataclasses.replace(decoration, args=args, kwargs=kwargs))
                    for decoration in reversed(self.decorations)
                ]

                return_ = self.decoratee(*args, **kwargs)

                for decoration in reversed(decorations):
                    decoration(return_)

            return return_

    @classmethod
    @typing.overload
    def __new__(cls, *, decoratee: Decoratee.Async[Params, Return], **kwargs) -> Decorated.Async[Params, Return]: ...

    @classmethod
    @typing.overload
    def __new__(cls, *, decoratee: Decoratee.Multi[Params, Return], **kwargs) -> Decorated.Multi[Params, Return]: ...

    @typing.final
    def __new__(cls, *, decoratee: Decoratee[Params, Return], **kwargs) -> Decorated[Params, Return]:
        if issubclass(cls, mixin := cls.Async if inspect.iscoroutinefunction(decoratee) else cls.Multi):
            return super().__new__(cls)  # noqa
        else:
            return type(f'{mixin.__name__}{cls.__name__}', (mixin, cls), dict(mixin.__dict__))(decoratee=decoratee)


#@dataclasses.dataclass(frozen=True)
#class Decorator[** Params, Return](abc.ABC):
#
#    @dataclasses.dataclass(frozen=True, kw_only=True)
#    class Async[** Params, Return](abc.ABC):
#        def __call__(self, decoratee: Decoratee.Async[Params, Return], /) -> Decorated.Async[Params, Return]:
#            if isinstance(decoratee, Decorated.Async):
#                return decoratee
#
#            assert isinstance(decoratee, Decoratee.Async)
#
#            return inspect.markcoroutinefunction(
#                functools.wraps(decoratee)(Decorated.Async[Params, Return](decoratee=decoratee))
#            )
#
#    @dataclasses.dataclass(frozen=True, kw_only=True)
#    class Multi[** Params, Return](abc.ABC):
#        def __call__(self, decoratee: Decoratee.Multi[Params, Return], /) -> Decorated.Multi[Params, Return]:
#            if isinstance(decoratee, Decorated.Multi):
#                return decoratee
#
#            assert isinstance(decoratee, Decoratee.Multi)
#
#            return functools.wraps(decoratee)(Decorated.Multi[Params, Return](decoratee=decoratee))
#
#    @typing.overload
#    def __call__(self, decoratee: Decoratee.Async[Params, Return], /) -> Decorated.Async[Params, Return]: ...
#
#    @typing.overload
#    def __call__(self, decoratee: Decoratee.Multi[Params, Return], /) -> Decorated.Multi[Params, Return]: ...
#
#    def __call__(self, decoratee: Decoratee[Params, Return], /) -> Decorated[Params, Return]:
#        mixin = self.Async if inspect.iscoroutinefunction(decoratee) else self.Multi
#        return type(f'{mixin.__name__}{type(self).__name__}', (mixin, type(self)), dict(mixin.__dict__))(
#            decoratee=decoratee
#        )
