import dataclasses
import typing

from .. import _key
from . import _async as Async, _base as Base, _multi as Multi  # noqa


Register = Base.Register

type Decoratee[** Params, Return] = Async.Decoratee[Params, Return] | Multi.Decoratee[Params, Return]
type Decorated[** Params, Return] = Async.Decorated[Params, Return] | Multi.Decorated[Params, Return]


Decoration = Async.Decoration | Multi.Decoration


@dataclasses.dataclass(frozen=True, kw_only=True)
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
        if isinstance(getattr(decoratee, 'register', None), Register):
            decoratee: Decorated[Params, Return]
        else:
            decoratee: _key.Decorated[Params, Return] = _key.Decorator(self._prefix, self._suffix)(decoratee)

            # Create all the register links that lead up to the entrypoint decoration.
            for i in range(len(decoratee.key)):
                self.register.links.setdefault(decoratee.key[:i], set()).add(decoratee.key[i])
            self.register.links.setdefault(decoratee.key, set())

            decoratee.register = self.register
            decoratee: Decorated[Params, Return]

            # Add the entrypoint decoration to the register.

        decorated: Decorated[Params, Return] = decoratee

        self.register.decorateds[decorated.key] = decoratee

        return decorated
