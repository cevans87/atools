from __future__ import annotations
import dataclasses
import typing

from .. import _key


@dataclasses.dataclass(frozen=True, kw_only=True)
class Register[_Decorated]:
    decorateds: dict[_key.Key, _Decorated] = dataclasses.field(default_factory=dict)
    links: dict[_key.Key, set[_key.Name]] = dataclasses.field(default_factory=dict)


class Decorated[_Decorated](_key.Base.Decorated, typing.Protocol):
    register: Register[_Decorated]


type Decoration[_Decorated] = Register[_Decorated]


@dataclasses.dataclass(frozen=True, kw_only=True)
class Decorator[_Decorated](_key.Decorator):
    register: Register[_Decorated] = Register()
