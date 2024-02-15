import dataclasses
import enum
import typing

import atools


@atools.CLI()
def positional_only_without_defaults(foo: int, bar: str, /) -> None:
    """Demo for CLI entrypoint with positional-only args without defaults.

    Ex:
        python3 -m demo cli postional_only_without_defaults 42 Hi!
    """
    print(locals())


@atools.CLI()
def positional_or_keyword_without_defaults(foo: float, bar: bool) -> None:
    """Demo for CLI entrypoint with positional-or-keyword args without defaults.

    Ex:
        python3 -m demo cli keyword_only_without_defaults --foo 3.14 --bar True
    """
    print(locals())


@atools.CLI()
def keyword_only_without_defaults(*, foo: float, bar: bool) -> None:
    """Demo for CLI entrypoint with keyword-only args without defaults.

    Ex:
        python3 -m demo cli keyword_only_without_defaults --foo 3.14 --bar True
    """
    print(locals())


@atools.CLI()
def positional_only_with_defaults(foo: int = 0, bar: str = 'Bye!', /) -> None:
    """Demo for CLI entrypoint with positional-only args with defaults.

    Ex:
        python3 -m demo cli keyword_only_without_defaults
        python3 -m demo cli keyword_only_without_defaults 42
        python3 -m demo cli keyword_only_without_defaults 42 Hi!
    """
    print(locals())


@atools.CLI()
def positional_or_keyword_with_defaults(foo: float = 0.0, bar: bool = False) -> None:
    """Demo for CLI entrypoint with positional-or-keyword args with defaults.

    Ex:
        python3 -m demo cli keyword_only_without_defaults
        python3 -m demo cli keyword_only_without_defaults --foo 3.14
        python3 -m demo cli keyword_only_without_defaults --bar True
        python3 -m demo cli keyword_only_without_defaults --foo 3.14 --bar True
        python3 -m demo cli keyword_only_without_defaults --foo 3.14 --bar True
    """
    print(locals())


@atools.CLI()
def keyword_only_with_defaults(*, foo: float = 0.0, bar: bool = False) -> None:
    """Demo for CLI entrypoint with keyword-only args with defaults.

    Ex:
        python3 -m demo cli keyword_only_without_defaults
        python3 -m demo cli keyword_only_without_defaults --foo 42.0
        python3 -m demo cli keyword_only_without_defaults --bar True
        python3 -m demo cli keyword_only_without_defaults --foo 42.0 --bar True
        python3 -m demo cli keyword_only_without_defaults --foo 42.0 --bar True
    """
    print(locals())


class MetasyntacticEnum(enum.Enum):
    foo = 1
    bar = 2
    baz = 3


@atools.CLI()
def enum(arg: MetasyntacticEnum, /) -> None:
    """Demo for CLI entrypoint with Enum argument.

    Ex:
        python3 -m demo cli enum foo
        python3 -m demo cli enum bar
        python3 -m demo cli enum baz
    """
    print(locals())


@atools.CLI()
def optional(arg: typing.Optional[int]) -> None:
    """Demo for CLI entrypoint with typing.Optional argument.

    Ex:
        python3 -m demo cli optional None
        python3 -m demo cli optional 42
    """
    print(f'{arg=!r}')


@atools.CLI()
def union(arg: typing.Union[bool, float, int, str, None]) -> None:
    """Demo for CLI entrypoint with typing.Union argument.

    Ex:
        python3 -m demo cli union True
        python3 -m demo cli union 3.14
        python3 -m demo cli union 42
        python3 -m demo cli union Hi!
        python3 -m demo cli union None
    """
    print(locals())


@atools.CLI()
def union_type(arg: bool | float | int | str | None) -> None:
    """Demo for CLI entrypoint with types.UnionType argument.

    Ex:
        python3 -m demo cli union True
        python3 -m demo cli union 3.14
        python3 -m demo cli union 42
        python3 -m demo cli union Hi!
        python3 -m demo cli union None
    """
    print(locals())


@atools.CLI()
def literal(arg: typing.Literal['foo', 'bar', 'baz']) -> None:
    """Demo for CLI entrypoint with Literal argument.

    Ex:
        python3 -m demo cli literal foo
        python3 -m demo cli literal bar
        python3 -m demo cli literal baz
    """
    print(locals())


@dataclasses.dataclass(frozen=True)
class CustomType:
    data: bool | float | int | str | None | dict | list | set | tuple


@atools.CLI()
def custom_type(arg: CustomType) -> None:
    """Demo for CLI entrypoint with CustomType argument.

    Ex:
        python3 -m demo cli custom_type True
        python3 -m demo cli custom_type 3.14
        python3 -m demo cli custom_type 42
        python3 -m demo cli custom_type Hi!
        python3 -m demo cli custom_type None
        python3 -m demo cli custom_type "{1: 2}"
        python3 -m demo cli custom_type "[1, 2, 3]"
        python3 -m demo cli custom_type "{1, 2, 3}"
        python3 -m demo cli custom_type "(1, 2, 3)"
    """
    print(locals())


@atools.CLI()
def var_positional(*args: int | float) -> None:
    """Demo for CLI entrypoint with var-positional arguments.

    Ex:
        python3 -m demo cli var_positional 1 1 2 3 5 7
        python3 -m demo cli var_positional 0 1.618 3.14
    """
    print(locals())


@atools.CLI()
def var_keyword(**kwargs: int | float | str) -> None:
    """Demo for CLI entrypoint with var-keyword arguments.

    Ex:
        python3 -m demo cli var_keyword --foo 42 --bar 3.14 --baz Hi!
    """
    print(locals())


@atools.CLI()
def _hidden(foo: int) -> None:
    """Demo for CLI entrypoint that is hidden from help text.

    Ex:
        python3 -m demo cli -h
        python3 -m demo cli _hidden 42
    """
    print(locals())


if __name__ == '__main__':
    atools.CLI(__name__).run()
