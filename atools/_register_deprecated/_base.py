from __future__ import annotations
import dataclasses
import typing

from .. import bofdsfdfsa


@dataclasses.dataclass(frozen=True, kw_only=True)
class Register[Decorated]:
    decorateds: dict[bofdsfdfsa.Key, Decorated] = dataclasses.field(default_factory=dict)
    links: dict[bofdsfdfsa.Key, set[bofdsfdfsa.Name]] = dataclasses.field(default_factory=dict)


class Decoratee[Call](typing.Protocol):
    __call__: Call


@typing.runtime_checkable
class Decorated[Call](bofdsfdfsa.Base.Decorated, typing.Protocol):
    __call__: Call
    register: Decorated[Call]


type Decoration[Decorated] = Register[Decorated]


@dataclasses.dataclass(frozen=True, kw_only=True)
class Decorator[Decorated](bofdsfdfsa.Decorator):
    register: Register[Decorated] = Register()
