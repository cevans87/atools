from __future__ import annotations

import abc
import asyncio
import builtins
import concurrent.futures
import contextlib
import dataclasses
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
class HerdFollower[Result](abc.ABC):
    future: asyncio.Future[Result] | concurrent.futures.Future[Result]


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncHerdFollower[Result](HerdFollower[Result]):
    future: asyncio.Future[Result] = dataclasses.field(default_factory=asyncio.Future)


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiHerdFollower[Result](HerdFollower[Result]):
    future: concurrent.futures.Future[Result] = dataclasses.field(default_factory=concurrent.futures.Future)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Pending[Result](abc.ABC):
    future: asyncio.Future[Result] | concurrent.futures.Future[Result]


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncPending[Result](Pending[Result]):
    future: asyncio.Future[Result] = dataclasses.field(default_factory=asyncio.Future)


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiPending[Result](Pending[Result]):
    future: concurrent.futures.Future[Result] = dataclasses.field(default_factory=concurrent.futures.Future)


class Decoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, typing.Awaitable[Return] | Return]


class AsyncDecoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, typing.Awaitable[Return]]


class MultiDecoratee[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, Return]


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](abc.ABC):

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
class BoundContext[** Params, Return](Context[Params, Return], abc.ABC):
    instance: Instance


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncBoundContext[** Params, Return](AsyncContext[Params, Return], BoundContext[Params, Return], abc.ABC):
    ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiBoundContext[** Params, Return](MultiContext[Params, Return], BoundContext[Params, Return], abc.ABC):
    ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class CreateContext[** Params, Return](abc.ABC):

    BoundCreateContext: typing.ClassVar[type[BoundCreateContext]]
    Context: typing.ClassVar[type[Context]] = Context

    @typing.overload
    def __call__(
        self: AsyncCreateContext[Params, Return],
        args: Params.args,
        kwargs: Params.kwargs,
    ) -> AsyncContext[Params, Return] | ShortCircuit[Return]: ...

    @typing.overload
    def __call__(
        self: MultiCreateContext[Params, Return],
        args: Params.args,
        kwargs: Params.kwargs,
    ) -> MultiContext[Params, Return] | ShortCircuit[Return]: ...

    def __call__(self, args, kwargs):
        return self.Context[Params, Return](args=args, kwargs=kwargs)

    def __get__(self, instance: Instance, owner) -> BoundCreateContext[Params, Return]:
        return self.BoundCreateContext[Params, Return](instance=instance)


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncCreateContext[** Params, Return](CreateContext[Params, Return], abc.ABC):
    BoundCreateContext: typing.ClassVar[type[AsyncBoundCreateContext]]
    Context: typing.ClassVar[type[AsyncContext]] = AsyncContext


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiCreateContext[** Params, Return](CreateContext[Params, Return], abc.ABC):
    BoundCreateContext: typing.ClassVar[type[MultiBoundCreateContext]]
    Context: typing.ClassVar[type[MultiContext]] = MultiContext

    def __call__(
        self,
        args: Params.args,
        kwargs: Params.kwargs,
    ) -> MultiContext[Params, Return] | ShortCircuit[Return]:
        return self.Context[Params, Return](args=args, kwargs=kwargs)


@dataclasses.dataclass(frozen=True, kw_only=True)
class BoundCreateContext[** Params, Return](CreateContext[Params, Return], abc.ABC):
    instance: Instance


CreateContext.BoundCreateContext = BoundCreateContext


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncBoundCreateContext[** Params, Return](
    AsyncCreateContext[Params, Return], BoundCreateContext[Params, Return], abc.ABC
):
    ...


AsyncCreateContext.BoundCreateContext = AsyncBoundCreateContext


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiBoundCreateContext[** Params, Return](
    MultiCreateContext[Params, Return], BoundCreateContext[Params, Return], abc.ABC
):
    ...


MultiCreateContext.BoundCreateContext = MultiBoundCreateContext


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
    lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    register: Register
    register_key: Register.Key
    __name__: str
    __qualname__: str

    __call__: typing.ClassVar[typing.Callable[Params, typing.Awaitable[Return] | Return]]

    BoundDecorated: typing.ClassVar[type[BoundDecorated]]
    CreateContext: typing.ClassVar[type[CreateContext]] = CreateContext

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

    def __call__(self): ...

    def __get__(self, instance, owner):
        with self.lock:
            return self.BoundDecorated[Params, Return](
                create_contexts=tuple([
                    create_context.__get__(instance, None) for create_context in self.create_contexts
                ]),
                decoratee=self.decoratee,
                instance=instance,
                register=self.register,
                register_key=self.register_key,
                __name__=self.__name__,
                __qualname__=self.__qualname__,
            )

    #@staticmethod
    #def create_context(
    #    create_context: MultiCreateContext[Params, Return],
    #    args: Params.args,
    #    kwargs: Params.kwargs,
    #) -> AsyncBoundContext[Params, Return]:
    #    return create_context(args=args, kwargs=kwargs)

    @staticmethod
    def norm_kwargs(kwargs: Params.kwargs) -> Params.kwargs:
        return dict(sorted(kwargs.items()))

    @staticmethod
    def norm_args(args: Params.args) -> Params.args:
        return args


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncDecorated[** Params, Return](Decorated[Params, Return]):
    create_contexts: tuple[AsyncCreateContext[Params, Return], ...] = ()
    decoratee: AsyncDecoratee[Params, Return]

    _is_coroutine_marker: typing.ClassVar = inspect._is_coroutine_marker  # noqa
    BoundDecorated: typing.ClassVar[type[AsyncBoundDecorated]]
    CreateContext: typing.ClassVar[type[AsyncCreateContext]] = AsyncCreateContext

    async def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return:
        args, kwargs = self.norm_args(args), self.norm_kwargs(kwargs)
        async with contextlib.AsyncExitStack() as stack:
            contexts = []

            for create_context in self.create_contexts:
                match create_context(args=args, kwargs=kwargs):
                    case HerdFollower(future=future):
                        return_ = await future
                        break
                    case ShortCircuit(value=return_):
                        break
                    case Context() as context:
                        contexts.append(context)
                        await stack.enter_async_context(context)
            else:
                return_ = await self.decoratee(*args, **kwargs)

            for context in reversed(contexts):
                await context(return_=return_)

        return return_


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiDecorated[** Params, Return](Decorated[Params, Return]):
    create_contexts: tuple[MultiCreateContext[Params, Return], ...] = ()
    decoratee: MultiDecoratee[Params, Return]

    BoundDecorated: typing.ClassVar[type[MultiBoundDecorated]]
    CreateContext: typing.ClassVar[type[MultiCreateContext]] = MultiCreateContext

    def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> Return:
        args, kwargs = self.norm_args(args), self.norm_kwargs(kwargs)
        with contextlib.ExitStack() as stack:
            contexts = []

            for create_context in self.create_contexts:
                match create_context(args=args, kwargs=kwargs):
                    case HerdFollower(future=future):
                        return_ = concurrent.futures.wait(future)
                        break
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

    CreateContext: typing.ClassVar[type[BoundCreateContext]] = BoundCreateContext

    def norm_args(self, args: Params.args) -> Params.args:
        return tuple([self.instance, *args])


Decorated.BoundDecorated = BoundDecorated


@dataclasses.dataclass(frozen=True, kw_only=True)
class AsyncBoundDecorated[** Params, Return](AsyncDecorated[Params, Return], BoundDecorated[Params, Return], abc.ABC):
    CreateContext: typing.ClassVar[type[AsyncBoundCreateContext]] = AsyncBoundCreateContext


AsyncDecorated.BoundDecorated = AsyncBoundDecorated


@dataclasses.dataclass(frozen=True, kw_only=True)
class MultiBoundDecorated[** Params, Return](MultiDecorated[Params, Return], BoundDecorated[Params, Return], abc.ABC):
    CreateContext: typing.ClassVar[type[MultiBoundCreateContext]] = MultiBoundCreateContext


MultiDecorated.BoundDecorated = MultiBoundDecorated


@dataclasses.dataclass(frozen=True)
class Decorator[** Params, Return]:
    name: Name = ...
    register: typing.ClassVar[Register] = Register()

    @typing.overload
    def __call__(self, decoratee: AsyncDecoratee[Params, Return], /) -> AsyncDecorated[Params, Return]: ...

    @typing.overload
    def __call__(self, decoratee: MultiDecoratee[Params, Return], /) -> MultiDecorated[Params, Return]: ...

    def __call__(self, decoratee, /):
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
