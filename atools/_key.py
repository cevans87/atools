from __future__ import annotations
import annotated_types
import dataclasses
import re
import typing


_Name = typing.Annotated[str, annotated_types.Predicate(lambda name: re.match(r'^[.a-z]*$', name) is not None)]


class _Decoration(
    tuple[typing.Annotated[str, annotated_types.Predicate(lambda value: re.match(r'^[a-z]*$', value) is not None)], ...]
):

    @staticmethod
    def of_name(name: _Name) -> _Decoration:
        return _Decoration(tuple(re.sub(r'.<.*>', '', name).split('.')))


class _Decoratee[** Params, Return](typing.Callable[Params, Return]):
    __call__: typing.Callable[Params, Return]


class _Decorated[** Params, Return](_Decoratee[Params, Return]):
    key: _Decoration


@dataclasses.dataclass(frozen=True)
class _Decorator:
    _name: _Name = ...

    Decorated: typing.ClassVar[type[_Decorated]] = _Decorated
    Key: typing.ClassVar[type[_Decoration]] = _Decoration
    Name: typing.ClassVar[type[_Name]] = _Name

    def __init__(self, _name: _Name = ..., /) -> None:
        object.__setattr__(self, '_name', _name if _name is ... else re.sub(r'.<.*>', '', _name))

    def __call__[** Params, Return](self, decoratee: _Decoratee[Params, Return], /) -> _Decorated[Params, Return]:
        decoratee.key = _Decoration.of_name(
            self._name if self._name is not ... else f'{decoratee.__module__}.{decoratee.__qualname__}'
        )
        decoratee: _Decorated

        return decoratee


Key = _Decorator
