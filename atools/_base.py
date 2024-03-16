from __future__ import annotations
import abc
import asyncio
import builtins
import contextlib
import dataclasses
import importlib
import inspect
import re
import threading
import types
import typing


type Instance = object
type Name = typing.Annotated[str, annotated_types.Predicate(str.isidentifier)]  # noqa


class Exception(builtins.Exception):  # noqa
    ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class ShortCircuit[Return]:
    value: Return


@dataclasses.dataclass(frozen=True, kw_only=True)
class Pending(abc.ABC):
    event: asyncio.Event | threading.Event


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncPending(Pending):
    event: asyncio.Event = dataclasses.field(default_factory=lambda: asyncio.Event())


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiPending(Pending):
    event: threading.Event = dataclasses.field(default_factory=lambda: threading.Event())


class Decoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, typing.Awaitable[Return] | Return]


class AsyncDecoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, typing.Awaitable[Return]]


class MultiDecoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, Return]


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](abc.ABC):
    signature: inspect.Signature
    args: Params.args
    kwargs: Params.kwargs

    def __call__(self, return_: Return) -> None:
        pass


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

    async def __aexit__[ExcType: type[BaseException]](
        self, exc_type: type[ExcType] | None, exc_val: ExcType | None, exc_tb: types.TracebackType | None
    ) -> None: ...


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

    def __exit__[ExcType: type[BaseException]](
        self, exc_type: type[ExcType] | None, exc_val: ExcType | None, exc_tb: types.TracebackType | None
    ) -> None: ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class BoundContext[** Params, Return](Context[Params, Return], abc.ABC):
    instance: Instance


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncBoundContext[** Params, Return](BoundContext[Params, Return], AsyncContext[Params, Return], abc.ABC):
    ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiBoundContext[** Params, Return](BoundContext[Params, Return], MultiContext[Params, Return], abc.ABC):
    ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class CreateContext[** Params, Return](abc.ABC):
    signature: inspect.Signature

    @typing.overload
    @property
    def context_t(
        self: AsyncCreateContext[Params, Return]
    ) -> type[AsyncContext[Params, Return]]: ...

    @typing.overload
    @property
    def context_t(
        self: MultiCreateContext[Params, Return]
    ) -> type[MultiContext[Params, Return]]: ...

    @property
    def context_t(self) -> type[Context[Params, Return]]:
        match self:
            case AsyncCreateContext():
                return importlib.import_module(self.__module__).AsyncContext
            case MultiCreateContext():
                return importlib.import_module(self.__module__).MultiContext

    @property
    def bound_create_context_t(self) -> type[BoundCreateContext[Params, Return]]:
        match self:
            case AsyncCreateContext():
                return AsyncBoundCreateContext
            case MultiCreateContext():
                return MultiBoundCreateContext

    def __call__(self, args: Params.args, kwargs: Params.kwargs) -> Context[Params, Return] | ShortCircuit[Return]:
        return self.context_t[Params, Return](args=args, kwargs=kwargs)

    def __get__(self, instance: Instance, owner) -> BoundCreateContext[Params, Return]:
        return self.bound_create_context_t[Params, Return](instance=instance, signature=self.signature)


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncCreateContext[** Params, Return](CreateContext[Params, Return], abc.ABC):
    ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiCreateContext[** Params, Return](CreateContext[Params, Return], abc.ABC):
    ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class BoundCreateContext[** Params, Return](CreateContext[Params, Return], abc.ABC):
    instance: Instance

    @typing.overload
    @property
    def context_t(
        self: AsyncBoundCreateContext[Params, Return]
    ) -> type[AsyncBoundContext[Params, Return]]:
        ...

    @typing.overload
    @property
    def context_t(
        self: MultiBoundCreateContext[Params, Return]
    ) -> type[MultiBoundContext[Params, Return]]:
        ...

    @property
    def context_t(self) -> type[Context[Params, Return]]:
        match self:
            case AsyncBoundCreateContext():
                return importlib.import_module(self.__module__).AsyncBoundContext
            case MultiBoundCreateContext():
                return importlib.import_module(self.__module__).MultiBoundContext

    def __call__(self, args: Params.args, kwargs: Params.kwargs) -> Context[Params, Return] | ShortCircuit[Return]:
        return self.context_t[Params, Return](args=args, instance=self.instance, kwargs=kwargs)


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncBoundCreateContext[** Params, Return](BoundCreateContext[Params, Return], abc.ABC):
    ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiBoundCreateContext[** Params, Return](BoundCreateContext[Params, Return], abc.ABC):
    ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class Register(abc.ABC):
    class Key(tuple[str, ...]):
        def __str__(self) -> str:
            return '.'.join(self)

    decoratees: dict[Key, Decoratee] = dataclasses.field(default_factory=dict)
    links: dict[Key, set[Name]] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Decorated[** Params, Return](abc.ABC):
    create_contexts: tuple[CreateContext[Params, Return], ...] = ()
    decoratee: Decoratee[Params, Return]
    register: Register
    register_key: Register.Key
    __name__: str
    __qualname__: str

    __call__: typing.ClassVar[typing.Callable[Params, typing.Awaitable[Return] | Return]]

    @typing.overload
    @property
    def bound_decorated_t(
        self: AsyncDecorated[Params, Return] | AsyncBoundDecorated[Params, Return]
    ) -> type[AsyncBoundDecorated[Params, Return]]:
        ...

    @typing.overload
    @property
    def bound_decorated_t(
        self: MultiDecorated[Params, Return] | MultiBoundDecorated[Params, Return]
    ) -> type[MultiBoundDecorated[Params, Return]]:
        ...

    @property
    def bound_decorated_t(self) -> type[BoundDecorated[Params, Return]]:
        match self:
            case AsyncDecorated() | AsyncBoundDecorated():
                return importlib.import_module(self.__module__).AsyncBoundDecorated
            case MultiDecorated() | MultiBoundDecorated():
                return importlib.import_module(self.__module__).MultiBoundDecorated

    @typing.overload
    @property
    def create_context_t(
        self: AsyncDecorated[Params, Return]
    ) -> type[AsyncCreateContext[Params, Return]]: ...

    @typing.overload
    @property
    def create_context_t(
        self: MultiDecorated[Params, Return]
    ) -> type[MultiCreateContext[Params, Return]]: ...

    @typing.overload
    @property
    def create_context_t(
        self: AsyncBoundDecorated[Params, Return]
    ) -> type[AsyncBoundCreateContext[Params, Return]]:
        ...

    @typing.overload
    @property
    def create_context_t(
        self: MultiBoundDecorated[Params, Return]
    ) -> type[MultiBoundCreateContext[Params, Return]]:
        ...

    @property
    def create_context_t(self) -> type[CreateContext[Params, Return]]:
        match self:
            case AsyncDecorated():
                return importlib.import_module(self.__module__).AsyncCreateContext
            case MultiDecorated():
                return importlib.import_module(self.__module__).MultiCreateContext
            case AsyncBoundDecorated():
                return importlib.import_module(self.__module__).AsyncBoundCreateContext
            case MultiBoundDecorated():
                return importlib.import_module(self.__module__).MultiBoundCreateContext

    @typing.overload
    def __get__(
        self: AsyncDecorated[Params, Return],
        instance: Instance,
        owner
    ) -> AsyncBoundDecorated[Params, Return]: ...

    @typing.overload
    def __get__(
        self: MultiDecorated[Params, Return],
        instance: Instance,
        owner
    ) -> MultiBoundDecorated[Params, Return]: ...

    def __get__(self, instance, owner) -> BoundDecorated[Params, Return]:
        return self.bound_decorated_t[Params, Return](
            create_contexts=tuple([create_context.__get__(instance, None) for create_context in self.create_contexts]),
            decoratee=self.decoratee,
            instance=instance,
            register=self.register,
            register_key=self.register_key,
            __name__=self.__name__,
            __qualname__=self.__qualname__,
        )


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncDecorated[** Params, Return](Decorated[Params, Return]):
    create_contexts: tuple[AsyncCreateContext[Params, Return], ...] = ()
    decoratee: AsyncDecoratee[Params, Return]

    _is_coroutine_marker: typing.ClassVar = inspect._is_coroutine_marker  # noqa

    async def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return:
        async with contextlib.AsyncExitStack() as stack:
            contexts = []

            for create_context in self.create_contexts:
                match create_context(args=args, kwargs=kwargs):
                    case ShortCircuit(value=return_):
                        break
                    case Context() as context:
                        contexts.append(context)
                        await stack.enter_async_context(context)
            else:
                return_ = self.decoratee(*args, **kwargs)

            for context in reversed(contexts):
                context(return_=return_)

        return return_


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiDecorated[** Params, Return](Decorated[Params, Return]):
    create_contexts: tuple[MultiCreateContext[Params, Return], ...] = ()
    decoratee: MultiDecoratee[Params, Return]

    def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return:
        with contextlib.ExitStack() as stack:
            contexts = []

            for create_context in self.create_contexts:
                match create_context(args=args, kwargs=kwargs):
                    case ShortCircuit(value=return_):
                        break
                    case Context() as context:
                        contexts.append(context)
                        stack.enter_context(context)
            else:
                return_ = self.decoratee(*args, **kwargs)

            for context in reversed(contexts):
                context(return_=return_)

        return return_


@dataclasses.dataclass(frozen=True, kw_only=True)
class BoundDecorated[** Params, Return](Decorated[Params, Return], abc.ABC):
    instance: object

    @property
    def create_context_t(self) -> type[CreateContext[Params, Return]]:
        return BoundCreateContext[Params, Return]

    @typing.overload
    async def __call__(
        self: AsyncBoundDecorated[Params, Return],
        *args: Params.args,
        **kwargs: Params.kwargs,
    ) -> Return: ...

    @typing.overload
    def __call__(
        self: MultiBoundDecorated[Params, Return],
        *args: Params.args,
        **kwargs: Params.kwargs,
    ) -> Return: ...

    def __call__(
        self: AsyncBoundDecorated[Params, Return] | MultiBoundDecorated[Params, Return],
        *args: Params.args,
        **kwargs: Params.kwargs,
    ) -> typing.Awaitable[Return] | Return: ...

    del __call__

    @staticmethod
    @typing.overload
    def create_context(
        create_context: AsyncBoundCreateContext[Params, Return],
        args: Params.args,
        kwargs: Params.kwargs,
    ) -> AsyncBoundContext[Params, Return]: ...

    @staticmethod
    @typing.overload
    def create_context(
        create_context: MultiBoundCreateContext[Params, Return],
        args: Params.args,
        kwargs: Params.kwargs,
    ) -> MultiBoundContext[Params, Return]: ...

    @staticmethod
    def create_context(
        create_context: BoundCreateContext[Params, Return],
        args: Params.args,
        kwargs: Params.kwargs,
    ) -> BoundContext[Params, Return]:
        return create_context(args=args, kwargs=kwargs)


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncBoundDecorated[** Params, Return](BoundDecorated[Params, Return], AsyncDecorated[Params, Return], abc.ABC):

    async def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return:
        async with contextlib.AsyncExitStack() as stack:
            contexts = []

            for create_context in self.create_contexts:
                match create_context(args=args, kwargs=kwargs):
                    case ShortCircuit(value=return_):
                        break
                    case Context() as context:
                        contexts.append(context)
                        await stack.enter_async_context(context)
            else:
                return_ = self.decoratee(self.instance, *args, **kwargs)

            for context in reversed(contexts):
                context(return_=return_)

        return return_


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiBoundDecorated[** Params, Return](BoundDecorated[Params, Return], MultiDecorated[Params, Return], abc.ABC):

    def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return:
        with contextlib.ExitStack() as stack:
            contexts = []

            for create_context in self.create_contexts:
                match create_context(args=args, kwargs=kwargs):
                    case ShortCircuit(value=return_):
                        break
                    case Context() as context:
                        contexts.append(context)
                        stack.enter_context(context)
            else:
                return_ = self.decoratee(self.instance, *args, **kwargs)

            for context in reversed(contexts):
                context(return_=return_)

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
        register_key = Register.Key([*name.split('.')])

        for i in range(len(register_key)):
            self.register.links.setdefault(register_key[:i], set()).add(register_key[i])
        self.register.links.setdefault(register_key, set())

        if inspect.iscoroutinefunction(decoratee):
            decorated = AsyncDecorated[Params, Return](
                decoratee=decoratee,
                register=self.register,
                register_key=register_key,
                __name__=decoratee.__name__,
                __qualname__=decoratee.__qualname__,
            )
        else:
            decorated = MultiDecorated[Params, Return](
                decoratee=decoratee,
                register=self.register,
                register_key=register_key,
                __name__=decoratee.__name__,
                __qualname__=decoratee.__qualname__,
            )

        decorated.register.decoratees[decorated.register_key] = decorated

        return decorated

    @property
    def register_key(self) -> Register.Key:
        return Register.Key([] if self.name is ... else [*re.sub(r'.<.*>', '', self.name).split('.')])
