import dataclasses
import re
import typing

from . import _async as Async, _base as Base, _multi as Multi  # noqa

Name = Base.Name
Key = Base.Key

type Decoratee[** Params, Return] = Async.Decoratee[Params, Return] | Multi.Decoratee[Params, Return]
type Decorated[** Params, Return] = Async.Decorated[Params, Return] | Multi.Decorated[Params, Return]
type Decoration = Async.Decoration | Multi.Decoration


@dataclasses.dataclass(frozen=True)
class Decorator(Base.Decorator):

    @typing.overload
    def __call__[** Params, Return](
        self, decoratee: Async.Decoratee[Params, Return], /
    ) -> Async.Decorated[Params, Return]: ...

    @typing.overload
    def __call__[** Params, Return](
        self, decoratee: Multi.Decoratee[Params, Return], /
    ) -> Multi.Decorated[Params, Return]: ...

    def __call__[** Params, Return](self, decoratee: Decoratee[Params, Return], /) -> Decorated[Params, Return]:
        if isinstance(getattr(decoratee, 'key', None), Key):
            decoratee: Decorated[Params, Return]
        else:
            prefix = self._prefix if self._prefix is not ... else decoratee.__module__
            suffix = self._suffix if self._prefix is not ... or self._suffix is not ... else re.sub(
                r'.<.*>', '', decoratee.__qualname__
            )

            decoratee.key = Decorator(prefix, suffix).key
            decoratee: Decorated[Params, Return]

        decorated: Decorated[Params, Return] = decoratee

        return decorated

    @property
    def key(self) -> Key:
        return Key(tuple([
            *([] if self._prefix is ... else re.sub(r'.<.*>', '', self._prefix).split('.')),
            *([] if self._suffix is ... else re.sub(r'.<.*>', '', self._suffix).split('.')),
        ]))
