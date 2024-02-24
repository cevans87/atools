import annotated_types
import dataclasses
import re
import typing

type Name = typing.Annotated[str, annotated_types.Predicate(lambda name: re.match(r'^[.a-z]*$', name) is not None)]


class Key(tuple[typing.Annotated[str, annotated_types.Predicate(lambda value: re.search(
    r'^[a-z]*$', value,  # noqa
) is not None)], ...]): ...


Decoration = Key


class Decorated(typing.Protocol):
    key: Key


@dataclasses.dataclass(frozen=True)
class Decorator:
    _prefix: Name
    _suffix: Name
