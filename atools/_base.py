import abc
import builtins
import functools
import contextlib
import dataclasses
import inspect
import re
import types
import typing


type Name = typing.Annotated[str, annotated_types.Predicate(str.isidentifier)]  # noqa


class Exception(builtins.Exception):  # noqa
    ...


class Decoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, typing.Awaitable[Return] | Return]


class AsyncDecoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, typing.Awaitable[Return]]


class MultiDecoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, Return]


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](abc.ABC):
    args: Params.args = ...
    kwargs: Params.kwargs = ...
    return_: Return = ...
    signature: inspect.Signature

    @property
    def key(self):
        assert self.args is not ... and self.kwargs is not ...

        bound_arguments = self.signature.bind(*self.args, **self.kwargs)
        bound_arguments.apply_defaults()

        return bound_arguments.args, tuple(sorted(bound_arguments.kwargs.items()))


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContext[** Params, Return](Context[Params, Return], abc.ABC):
    async def __call__(self) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None:
        return None


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiContext[** Params, Return](Context[Params, Return], abc.ABC):

    def __call__(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None:
        return None


class Key(tuple[str, ...]):

    def __str__(self) -> str:
        return '.'.join(self)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Register(abc.ABC):
    decoratees: dict[Key, Decoratee] = dataclasses.field(default_factory=dict)
    links: dict[Key, set[Name]] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(kw_only=True)
class Decorated[** Params, Return](abc.ABC):
    contexts: tuple[Context[Params, Return], ...] = ()
    decoratee: Decoratee[Params, Return]
    key: Key
    register: Register

    __call__: typing.ClassVar[typing.Callable[Params, typing.Awaitable[Return] | Return]]


@dataclasses.dataclass(kw_only=True)
class AsyncDecorated[** Params, Return](Decorated[Params, Return]):
    contexts: tuple[AsyncContext[Params, Return], ...] = ()
    decoratee: AsyncDecoratee[Params, Return]

    async def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return:
        async with contextlib.AsyncExitStack() as stack:
            for context in self.contexts:
                await stack.enter_async_context(dataclasses.replace(context, args=args, kwargs=kwargs))

            return_ = await self.decoratee(*args, **kwargs)

            for context in reversed(self.contexts):
                await dataclasses.replace(context, args=args, kwargs=kwargs, return_=return_)()

        return return_


@dataclasses.dataclass(kw_only=True)
class MultiDecorated[** Params, Return](Decorated[Params, Return]):
    contexts: tuple[MultiContext[Params, Return], ...] = ()
    decoratee: MultiDecoratee[Params, Return]

    def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return:
        with contextlib.ExitStack() as stack:
            for context in self.contexts:
                stack.enter_context(dataclasses.replace(context, args=args, kwargs=kwargs))

            return_ = self.decoratee(*args, **kwargs)

            for context in reversed(self.contexts):
                dataclasses.replace(context, args=args, kwargs=kwargs, return_=return_)()

        return return_


@dataclasses.dataclass(frozen=True)
class Decorator[** Params, Return]:
    name: Name = ...
    register: typing.ClassVar[Register] = Register()

    @typing.overload
    def __call__(self, decoratee: AsyncDecoratee[Params, Return], /) -> AsyncDecorated[Params, Return]: ...

    @typing.overload
    def __call__(self, decoratee: MultiDecoratee[Params, Return], /) -> MultiDecorated[Params, Return]: ...

    def __call__(self, decoratee: Decoratee[Params, Return], /) -> Decorated[Params, Return]:

        name = self.name if self.name is not ... else (
            re.sub(r'.<.*>', '', '.'.join([decoratee.__module__, decoratee.__qualname__]))
        )
        key = Key([*name.split('.')])

        for i in range(len(key)):
            self.register.links.setdefault(key[:i], set()).add(key[i])
        self.register.links.setdefault(key, set())

        if inspect.iscoroutinefunction(decoratee):
            decorated = inspect.markcoroutinefunction(AsyncDecorated[Params, Return](
                decoratee=decoratee, key=key, register=self.register
            ))
        else:
            decorated = MultiDecorated[Params, Return](decoratee=decoratee, key=key, register=self.register)
        decorated = decorated.register.decoratees[decorated.key] = functools.wraps(decoratee)(decorated)

        return decorated

    @property
    def key(self) -> Key:
        return Key([] if self.name is ... else [*re.sub(r'.<.*>', '', self.name).split('.')])
