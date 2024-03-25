from __future__ import annotations

import abc
import builtins
import contextlib
import dataclasses
import inspect
import re
import threading
import types
import typing
import weakref

type Instance = object
type Name = typing.Annotated[str, annotated_types.Predicate(str.isidentifier)]  # noqa


class Exception(builtins.Exception):  # noqa
    ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class Register(abc.ABC):
    class Key(tuple[str, ...]):
        def __str__(self) -> str:
            return '.'.join(self)

    decorateds: dict[Key, Decorated] = dataclasses.field(default_factory=dict)
    links: dict[Key, set[Name]] = dataclasses.field(default_factory=dict)


class Decoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, typing.Awaitable[Return] | Return]


class AsyncDecoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, typing.Awaitable[Return]]


class MultiDecoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, Return]


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](abc.ABC):

    @typing.overload
    async def __call__(self: AsyncContext[Params, Return], return_: Return) -> None: ...

    @typing.overload
    def __call__(self: MultiContext[Params, Return], return_: Return) -> None: ...

    def __call__(self, return_): ...
    del __call__


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncContext[** Params, Return](Context[Params, Return], abc.ABC):

    async def __aenter__(self) -> typing.Self:
        return self

    @typing.overload
    async def __aexit__[ExcType: type[BaseException]](
        self, exc_type: type[ExcType], exc_val: ExcType, exc_tb: types.TracebackType
    ) -> object: ...

    @typing.overload
    async def __aexit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None: ...

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None: ...
    del __aexit__

    async def __call__(self, return_: Return) -> None: ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiContext[** Params, Return](Context[Params, Return], abc.ABC):

    def __enter__(self) -> typing.Self:
        return self

    @typing.overload
    def __exit__[ExcType: type[BaseException]](
        self, exc_type: type[ExcType], exc_val: ExcType, exc_tb: types.TracebackType
    ) -> object: ...

    @typing.overload
    def __exit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None: ...

    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...
    del __exit__

    def __call__(self, return_: Return) -> None: ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class CreateContext[** Params, Return](abc.ABC):
    Context: typing.ClassVar[type[Context]] = Context

    create_context_by_instance: weakref.WeakKeyDictionary[Instance, CreateContext] = dataclasses.field(
        default_factory=weakref.WeakKeyDictionary
    )
    instance: Instance = ...
    instance_lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)

    @typing.overload
    def __call__(
        self: AsyncCreateContext[Params, Return],
        args: Params.args,
        kwargs: Params.kwargs,
    ) -> AsyncContext[Params, Return] | Return: ...

    @typing.overload
    def __call__(
        self: MultiCreateContext[Params, Return],
        args: Params.args,
        kwargs: Params.kwargs,
    ) -> MultiContext[Params, Return] | Return: ...

    def __call__(self, args, kwargs):
        return self.Context[Params, Return](args=args, kwargs=kwargs)

    def __get__(self, instance: Instance, owner) -> typing.Self:
        return dataclasses.replace(self, instance=instance)


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncCreateContext[** Params, Return](CreateContext[Params, Return], abc.ABC):
    Context: typing.ClassVar[type[AsyncContext]] = AsyncContext

    async def __call__(
        self,
        args: Params.args,
        kwargs: Params.kwargs,
    ) -> AsyncContext[Params, Return] | Return:
        return AsyncContext[Params, Return](args=args, kwargs=kwargs)


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiCreateContext[** Params, Return](CreateContext[Params, Return], abc.ABC):
    Context: typing.ClassVar[type[MultiContext]] = MultiContext

    def __call__(
        self,
        args: Params.args,
        kwargs: Params.kwargs,
    ) -> MultiContext[Params, Return] | Return:
        return MultiContext[Params, Return](args=args, kwargs=kwargs)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Decorated[** Params, Return](abc.ABC):
    create_contexts: tuple[CreateContext[Params, Return], ...] = ()
    decoratee: Decoratee[Params, Return]
    instance: Instance = ...
    instance_lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    register: Register
    register_key: Register.Key
    __module__: str
    __name__: str
    __qualname__: str

    __call__: typing.ClassVar[typing.Callable[Params, typing.Awaitable[Return] | Return]]

    CreateContext: typing.ClassVar[type[CreateContext]] = CreateContext

    @typing.overload
    async def __call__(
        self: AsyncDecorated[Params, Return],
        *args: Params.args,
        **kwargs: Params.kwargs,
    ) -> Return: ...

    @typing.overload
    def __call__(
        self: MultiDecorated[Params, Return],
        *args: Params.args,
        **kwargs: Params.kwargs,
    ) -> Return: ...

    def __call__(self): ...
    del __call__

    @typing.overload
    def __get__(
        self: AsyncDecorated[Params, Return],
        instance: Instance,
        owner
    ) -> AsyncDecorated[Params, Return] | Return: ...

    @typing.overload
    def __get__(
        self: MultiDecorated[Params, Return],
        instance: Instance,
        owner
    ) -> MultiDecorated[Params, Return] | Return: ...

    def __get__(self, instance, owner):
        with self.instance_lock:
            return dataclasses.replace(
                self,
                create_contexts=tuple([
                    create_context.__get__(instance, owner) for create_context in self.create_contexts
                ]),
                instance=instance,
            )

    @staticmethod
    def norm_kwargs(kwargs: Params.kwargs) -> Params.kwargs:
        return dict(sorted(kwargs.items()))

    def norm_args(self, args: Params.args) -> Params.args:
        return args if self.instance is ... else [self.instance, *args]


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncDecorated[** Params, Return](Decorated[Params, Return]):
    create_contexts: tuple[AsyncCreateContext[Params, Return], ...] = ()
    decoratee: AsyncDecoratee[Params, Return]

    _is_coroutine_marker: typing.ClassVar = inspect._is_coroutine_marker  # noqa
    CreateContext: typing.ClassVar[type[AsyncCreateContext]] = AsyncCreateContext

    async def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return:
        args, kwargs = self.norm_args(args), self.norm_kwargs(kwargs)
        async with contextlib.AsyncExitStack() as stack:
            contexts = []

            for create_context in self.create_contexts:
                match await create_context(args=args, kwargs=kwargs):
                    case AsyncContext() as context:
                        contexts.append(await stack.enter_async_context(context))
                    case return_:
                        break
            else:
                return_ = await self.decoratee(*args, **kwargs)

            for context in reversed(contexts):
                await context(return_=return_)

        return return_


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiDecorated[** Params, Return](Decorated[Params, Return]):
    create_contexts: tuple[MultiCreateContext[Params, Return], ...] = ()
    decoratee: MultiDecoratee[Params, Return]

    CreateContext: typing.ClassVar[type[MultiCreateContext]] = MultiCreateContext

    def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return:
        args, kwargs = self.norm_args(args), self.norm_kwargs(kwargs)
        with contextlib.ExitStack() as stack:
            contexts = []

            for create_context in self.create_contexts:
                match create_context(args=args, kwargs=kwargs):
                    case MultiContext() as context:
                        contexts.append(stack.enter_context(context))
                    case return_:
                        break
            else:
                return_ = self.decoratee(*args, **kwargs)

            for context in reversed(contexts):
                context(return_=return_)

        return return_


@dataclasses.dataclass(frozen=True, kw_only=True)
class Decorator[** Params, Return]:
    global_register: typing.ClassVar[Register] = Register()
    register: Register = global_register

    @typing.overload
    def __call__(self, decoratee: AsyncDecoratee[Params, Return], /) -> AsyncDecorated[Params, Return]: ...

    @typing.overload
    def __call__(self, decoratee: MultiDecoratee[Params, Return], /) -> MultiDecorated[Params, Return]: ...

    def __call__(self, decoratee, /):

        register_key = Register.Key([
            *re.sub(r'.<.*>', '', '.'.join([decoratee.__module__, decoratee.__qualname__])).split('.')
        ])

        for i in range(len(register_key)):
            self.register.links.setdefault(register_key[:i], set()).add(register_key[i])
        self.register.links.setdefault(register_key, set())

        if inspect.iscoroutinefunction(decoratee):
            decorated_t = AsyncDecorated
        else:
            decorated_t = MultiDecorated
        decorated: Decorated[Params, Return] = decorated_t(
                decoratee=decoratee,
                register=self.register,
                register_key=register_key,
                __module__=decoratee.__module__,
                __name__=decoratee.__name__,
                __qualname__=decoratee.__qualname__,
            )

        decorated.register.decorateds[decorated.register_key] = decorated

        return decorated
