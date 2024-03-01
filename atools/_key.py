import annotated_types
import dataclasses
import re
import typing

from . import _contexts


type Name = typing.Annotated[str, annotated_types.Predicate(str.isidentifier)]  # noqa


class Key(tuple[str, ...]):
    ...


@typing.runtime_checkable
class Decorated[** Params, Return](_contexts.Decoratee[Params, Return], typing.Protocol):
    key: Key


@typing.runtime_checkable
class AsyncDecorated[** Params, Return](
    _contexts.AsyncDecoratee[Params, Return], Decorated[Params, Return], typing.Protocol
):
    ...


@typing.runtime_checkable
class MultiDecorated[** Params, Return](
    _contexts.MultiDecoratee[Params, Return], Decorated[Params, Return], typing.Protocol
):
    ...


@dataclasses.dataclass(frozen=True)
class Decorator[** Params, Return]:
    _prefix: Name = ...
    _suffix: Name = ...

    @typing.overload
    def __call__(self, decoratee: _contexts.AsyncDecoratee[Params, Return], /) -> AsyncDecorated[Params, Return]: ...

    @typing.overload
    def __call__(self, decoratee: _contexts.MultiDecoratee[Params, Return], /) -> MultiDecorated[Params, Return]: ...

    def __call__(self, decoratee: _contexts.Decoratee[Params, Return], /) -> Decorated[Params, Return]:
        assert not isinstance(decoratee, Decorated)
        if not isinstance(decoratee, _contexts.Decorated):
            decoratee = _contexts.Decorator()(decoratee)

        prefix = self._prefix if self._prefix is not ... else decoratee.__module__
        suffix = self._suffix if self._prefix is not ... or self._suffix is not ... else re.sub(
            r'.<.*>', '', decoratee.__qualname__
        )

        decoratee.key = Key([
            *([] if prefix is ... else re.sub(r'.<.*>', '', prefix).split('.')),
            *([] if suffix is ... else re.sub(r'.<.*>', '', suffix).split('.')),
        ])

        assert isinstance(decoratee, Decorated)

        decorated = decoratee

        return decorated

    @property
    def key(self) -> Key:
        return Key([
            *([] if self._prefix is ... else re.sub(r'.<.*>', '', self._prefix).split('.')),
            *([] if self._suffix is ... else re.sub(r'.<.*>', '', self._suffix).split('.')),
        ])
