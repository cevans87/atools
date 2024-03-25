import annotated_types
import dataclasses
import enum
import logging
import shlex
import types
import typing

import pytest

import atools


class FooEnum(enum.Enum):
    a = 'a'
    b = 'b'
    c = 'c'


class FooTuple(tuple):

    def __eq__(self, other) -> bool:
        return super().__eq__(other) and isinstance(other, type(self))


@dataclasses.dataclass(frozen=True)
class Arg[T]:
    arg: str = ...
    t: type[T] = ...
    default: T = ...
    expect: T = ...


args = [*map(lambda _args: Arg(*_args), [
    ('42', int, 0, 42),
    ('42', str, '0', '42'),
    ('3.14', float, 0.0, 3.14),
    ('True', bool, False, True),
    ('True', str, 'False', 'True'),
    ('False', bool, True, False),
    ('Hi!', str, 'Bye!', 'Hi!'),
    ('None', None, None, None),
    ('None', types.NoneType, None, None),
    ('"()"', tuple[()], (), ()),
    ('"()"', typing.Tuple[()], (), ()),
    ('"(1,)"', tuple[int], (0,), (1,)),
    ('"[1, 2, 3, 4]"', list[int], [], [1, 2, 3, 4]),
    ('"[1, 2, 3, 4]"', typing.List[int], [], [1, 2, 3, 4]),
    ('"(3.14, \'Hi!\', \'Bye!\')"', tuple[float, str, ...], (0.0, 'Meh!'), (3.14, 'Hi!', 'Bye!')),
    ('42', int | float | bool | str | None, 0, 42),
    ('3.14', int | float | bool | str | None, 0.0, 3.14),
    ('True', int | float | bool | str | None, False, True),
    ('False', int | float | bool | str | None, True, False),
    ('"\'Hi!\'"', int | float | bool | str | None, 'Bye!', 'Hi!'),
    ("None", int | float | bool | str | None, 42, None),
    ("42", typing.Optional[int], None, 42),
    ("None", typing.Optional[int], 42, None),
    ('"{True: {4.0: {42: \'yes!\'}}}"', dict[bool, dict[float, dict[int, str]]], {}, {True: {4.0: {42: 'yes!'}}}),
    ('"{1, 2, 3, 4}"', frozenset[int], frozenset(), frozenset({1, 2, 3, 4})),
    ('"{1, 2, 3, 4}"', set[int], set(), {1, 2, 3, 4}),
    ('b', FooEnum, FooEnum.a, FooEnum.b),
    ('\'(\"hi!\", \"bye!\")\'', FooTuple[str, ...], FooTuple(('Meh!',)), FooTuple(('hi!', 'bye!'))),
    ('42', typing.Annotated[int, 'foo annotation'], 0, 42),
])]


@pytest.mark.parametrize('arg', args)
def test_parses_positional_only(arg) -> None:

    @atools.CLI()
    def entrypoint(foo: arg.t, /) -> dict[str, arg.t]:
        return locals()

    # FIXME: change 'run' to take a string or decorated. Strings cause a lookup, decorateds run directly.
    assert atools.CLI().run(
        f'{entrypoint.__module__}.{entrypoint.__qualname__}', shlex.split(arg.arg)
    ) == {'foo': arg.expect}


@pytest.mark.parametrize('arg', args)
def test_parses_positional_only_with_default(arg) -> None:

    @atools.CLI()
    def entrypoint(foo: arg.t = arg.default, /) -> dict[str, arg.t]:
        return locals()

    assert entrypoint([]) == {'foo': arg.default}
    assert entrypoint(shlex.split(arg.arg)) == {'foo': arg.expect}


@pytest.mark.parametrize('arg', args)
def test_parses_positional_or_keyword(arg) -> None:

    @atools.CLI()
    def entrypoint(foo: arg.t) -> dict[str, arg.t]:
        return locals()

    with pytest.raises(SystemExit):
        entrypoint([])
    assert entrypoint(shlex.split(arg.arg)) == {'foo': arg.expect}


@pytest.mark.parametrize('arg', args)
def test_parses_positional_or_keyword_with_default(arg) -> None:

    @atools.CLI()
    def entrypoint(foo: arg.t = arg.default) -> dict[str, arg.t]:
        return locals()

    assert entrypoint([]) == {'foo': arg.default}
    assert entrypoint(shlex.split(f'--foo {arg.arg}')) == {'foo': arg.expect}


@pytest.mark.parametrize('arg', args)
def test_parses_keyword_only(arg) -> None:

    @atools.CLI()
    def entrypoint(*, foo: arg.t) -> dict[str, arg.t]:
        return locals()

    with pytest.raises(SystemExit):
        assert entrypoint([])
    assert entrypoint(shlex.split(f'--foo {arg.arg}')) == {'foo': arg.expect}


@pytest.mark.parametrize('arg', args)
def test_parses_keyword_only_with_default(arg) -> None:

    @atools.CLI()
    def entrypoint(*, foo: arg.t = arg.default) -> dict[str, arg.t]:
        return locals()

    assert entrypoint([]) == {'foo': arg.default}
    assert entrypoint(shlex.split(f'--foo {arg.arg}')) == {'foo': arg.expect}


@pytest.mark.parametrize('arg0,arg1', zip(args, [*args[1:], *args[:1]]))
def test_parses_positional_only_2(arg0, arg1) -> None:
    @atools.CLI()
    def entrypoint(foo: arg0.t, bar: arg1.t, /) -> dict[str, arg0.t | arg1.t]:
        return locals()

    assert entrypoint(shlex.split(f'{arg0.arg} {arg1.arg}')) == {'foo': arg0.expect, 'bar': arg1.expect}


@pytest.mark.parametrize('arg0,arg1', zip(args, [*args[1:], *args[:1]]))
def test_parses_positional_only_with_default_2(arg0, arg1) -> None:
    @atools.CLI()
    def entrypoint(foo: arg0.t = arg0.default, bar: arg1.t = arg1.default, /) -> dict[str, arg0.t | arg1.t]:
        return locals()

    assert entrypoint([]) == {'foo': arg0.default, 'bar': arg1.default}
    assert entrypoint(shlex.split(arg0.arg)) == {'foo': arg0.expect, 'bar': arg1.default}
    assert entrypoint(shlex.split(f'{arg0.arg} {arg1.arg}')) == {'foo': arg0.expect, 'bar': arg1.expect}


@pytest.mark.parametrize('arg0,arg1', zip(args, [*args[1:], *args[:1]]))
def test_parses_positional_or_keyword_2(arg0, arg1) -> None:
    @atools.CLI()
    def entrypoint(foo: arg0.t, bar: arg1.t) -> dict[str, arg0.t | arg1.t]:
        return locals()

    assert entrypoint(shlex.split(f'{arg0.arg} {arg1.arg}')) == {'foo': arg0.expect, 'bar': arg1.expect}


@pytest.mark.parametrize('arg0,arg1', zip(args, [*args[1:], *args[:1]]))
def test_parses_positional_or_keyword_with_default_2(arg0, arg1) -> None:
    @atools.CLI()
    def entrypoint(foo: arg0.t = arg0.default, bar: arg1.t = arg1.default) -> dict[str, arg0.t | arg1.t]:
        return locals()

    assert entrypoint([]) == {'foo': arg0.default, 'bar': arg1.default}
    assert entrypoint(shlex.split(f'--foo {arg0.arg}')) == {'foo': arg0.expect, 'bar': arg1.default}
    assert entrypoint(shlex.split(
        f'--foo {arg0.arg} --bar {arg1.arg}'
    )) == {'foo': arg0.expect, 'bar': arg1.expect}


@pytest.mark.parametrize('arg0,arg1', zip(args, [*args[1:], *args[:1]]))
def test_parses_keyword_only_2(arg0, arg1) -> None:

    @atools.CLI()
    def entrypoint(*, foo: arg0.t, bar: arg1.t) -> dict[str, arg0.t | arg1.t]:
        return locals()

    assert entrypoint(shlex.split(
        f'--foo {arg0.arg} --bar {arg1.arg}'
    )) == {'foo': arg0.expect, 'bar': arg1.expect}


@pytest.mark.parametrize('arg0,arg1', zip(args, [*args[1:], *args[:1]]))
def test_parses_keyword_only_with_default_2(arg0, arg1) -> None:

    @atools.CLI()
    def entrypoint(*, foo: arg0.t = arg0.default, bar: arg1.t = arg1.default) -> dict[str, arg0.t | arg1.t]:
        return locals()

    assert entrypoint([]) == {'foo': arg0.default, 'bar': arg1.default}
    assert entrypoint(shlex.split(f'--foo {arg0.arg}')) == {'foo': arg0.expect, 'bar': arg1.default}
    assert entrypoint(shlex.split(
        f'--foo {arg0.arg} --bar {arg1.arg}'
    )) == {'foo': arg0.expect, 'bar': arg1.expect}


@pytest.mark.parametrize(
    'arg', [Arg(*_args) for _args in [
        ('42', float),
        ('3.14', int),
        ('Hi!', bool),
        ('None', bool),
        ('"[1, 2, 3, 4]"', list[float]),
        ('"(42, False, 3.14, \'Hi!\')"', tuple[int, bool, float]),
        ('"(3.14, \'Hi!\', \'Bye!\')"', tuple[str, ...]),
        ('42', float | bool | str | None),
        ('3.14', int | bool | str | None),
        ('True', int | float | str | None),
        ('False', int | float | str | None),
        ('"\'Hi!\'"', int | float | bool | None),
        ("None", int | float | bool | str),
        ("42", typing.Optional[str]),
        ("3.14", typing.Optional[int]),
        ('"{True: {4.0: {42: \'yes!\'}}}"', dict[bool, dict[float, dict[int, int]]]),
        ('"{1, 2, 3, 4}"', frozenset[bool]),
        ('"{1, 2, 3, 4}"', set[str]),
        ('42', typing.Annotated[float, 'foo annotation']),
    ]])
def test_bad_arg_does_not_parse(arg: Arg) -> None:

    @atools.CLI()
    def entrypoint(foo: arg.t) -> ...: ...

    with pytest.raises(atools.CLI.Exception):
        entrypoint(shlex.split(arg.arg))


def test_execute_hidden_subcommand_works() -> None:

    @atools.CLI()
    def _foo(foo: str) -> dict[str, str]:
        return locals()

    assert '_foo' not in atools.CLI().cli().format_help()
    assert atools.CLI(prefix).run(shlex.split('_foo hidden_subcommand_works')) == {'foo': 'hidden_subcommand_works'}


def test_async_entrypoint_works() -> None:

    @atools.CLI()
    async def entrypoint(foo: int) -> dict[str, int]:
        return locals()

    assert entrypoint(shlex.split('42')) == {'foo': 42}


def test_dash_help_prints_parameter_annotation() -> None:
    @atools.CLI()
    def entrypoint(foo: typing.Annotated[int, 'This is my comment.']) -> ...: ...

    assert 'This is my comment.' in entrypoint.argument_parser.format_help()


def test_positional_only_without_default_works() -> None:
    @atools.CLI()
    def entrypoint(
        foo: typing.Annotated[int, 'Help text for foo.'],
        /,
    ) -> dict[str, int]:
        return locals()

    with pytest.raises(SystemExit):
        entrypoint(shlex.split(''))
    assert entrypoint(shlex.split('42')) == {'foo': 42}


def test_dash_help_prints_entrypoint_doc() -> None:
    @atools.CLI()
    def entrypoint(foo: int) -> ...:
        """What's up, Doc?"""

    assert """What's up, Doc?""" in entrypoint.argument_parser.format_help()


def test_annotation_log_level_of_logger_sets_choices() -> None:
    logger = logging.getLogger('test_annotated_of_logger_sets_choices')

    @atools.CLI()
    def entrypoint(foo: atools.CLI.Annotated.log_level(logger) = 'DEBUG') -> ...: ...

    for choice in typing.get_args(atools.CLI.Annotated.LogLevelStr):
        assert choice in entrypoint.argument_parser.format_help()


def test_annotation_log_level_of_logger_sets_log_level() -> None:
    logger = logging.getLogger('test_annotation_log_level_of_logger_sets_log_level')
    logger.setLevel(logging.NOTSET)

    @atools.CLI()
    def entrypoint(
        log_level: atools.CLI.Annotated.log_level(logger) = 'NOTSET',
    ) -> dict[str, atools.CLI.Annotated.LogLevel]:
        return locals()

    assert logger.level == logging.NOTSET

    assert entrypoint(shlex.split('--log-level CRITICAL')) == {'log_level': 'CRITICAL'}
    assert logger.level == logging.CRITICAL

    assert entrypoint(shlex.split('--log-level INFO')) == {'log_level': 'INFO'}
    assert logger.level == logging.INFO

    assert entrypoint(shlex.split('')) == {'log_level': 'NOTSET'}
    assert logger.level == logging.NOTSET


def test_annotation_log_level_of_name_sets_log_level() -> None:
    logger = logging.getLogger('test_annotation_log_level_of_name_sets_log_level')
    logger.setLevel(logging.NOTSET)

    @atools.CLI()
    def entrypoint(
        log_level: atools.CLI.Annotated.log_level('test_annotation_log_level_of_name_sets_log_level') = 'NOTSET',
    ) -> dict[str, atools.CLI.Annotated.LogLevel]:
        return locals()

    assert logger.level == logging.NOTSET

    assert entrypoint(shlex.split('--log-level CRITICAL')) == {'log_level': 'CRITICAL'}
    assert logger.level == logging.CRITICAL

    assert entrypoint(shlex.split('--log-level INFO')) == {'log_level': 'INFO'}
    assert logger.level == logging.INFO

    assert entrypoint(shlex.split('')) == {'log_level': 'NOTSET'}
    assert logger.level == logging.NOTSET


def test_annotation_verbose_sets_log_level() -> None:
    logger = logging.getLogger('test_annotation_verbose_sets_log_level')
    logger.setLevel(logging.NOTSET)

    @atools.CLI()
    def entrypoint(
        verbose: atools.CLI.Annotated.verbose(logger) = logging.CRITICAL + 10,
    ) -> dict[str, atools.CLI.Annotated.LogLevel]:
        return locals()

    assert logger.level == logging.NOTSET
    assert entrypoint(shlex.split('')) == {'verbose': logging.CRITICAL + 10}
    assert logger.level == logging.CRITICAL + 10
    assert entrypoint(shlex.split('-v')) == {'verbose': logging.CRITICAL}
    assert logger.level == logging.CRITICAL


def test_annotation_with_count_action_counts() -> None:
    @atools.CLI()
    def entrypoint(
        foo: typing.Annotated[
            int,
            annotated_types.Ge(0),
            atools.CLI.AddArgument[int](name_or_flags=['-f', '--foo'], action='count'),
        ] = 0,
    ) -> dict[str, int]:
        return locals()

    assert entrypoint(shlex.split('')) == {'foo': 0}
    assert entrypoint(shlex.split('--foo')) == {'foo': 1}
    assert entrypoint(shlex.split('--foo --foo')) == {'foo': 2}
    assert entrypoint(shlex.split('-f --foo')) == {'foo': 2}
    assert entrypoint(shlex.split('-ff')) == {'foo': 2}


def test_enum_help_text_shows_choices() -> None:

    @atools.CLI()
    def entrypoint(foo: FooEnum) -> dict[str, FooEnum]: ...

    assert '(\'a\', \'b\', \'c\')' in entrypoint.argument_parser.format_help()


def test_literal_help_text_shows_choices() -> None:

    @atools.CLI()
    def entrypoint(foo: typing.Literal[1, 2, 3]) -> dict[str, typing.Literal[1, 2, 3]]: ...

    assert '(\'1\', \'2\', \'3\')' in entrypoint.argument_parser.format_help()


def test_help_shows_type_annotation() -> None:

    @atools.CLI()
    def entrypoint(foo: dict[str, int]) -> ...: ...

    assert str(dict[str, int]) in entrypoint.argument_parser.format_help()


def test_enum_enforces_choices() -> None:

    @atools.CLI()
    def entrypoint(foo: FooEnum) -> dict[str, FooEnum]:
        return locals()

    with pytest.raises(atools.CLI.Exception):
        entrypoint(['d'])
    assert entrypoint(['a']) == {'foo': FooEnum.a}


def test_literal_enforces_choices() -> None:

    @atools.CLI()
    def entrypoint(foo: typing.Literal[1, 2, 3]) -> dict[str, typing.Literal[1, 2, 3]]:
        return locals()

    with pytest.raises(atools.CLI.Exception):
        entrypoint(['0'])
    assert entrypoint(['1']) == {'foo': 1}


def test_cli_names_enforce_subcommand_structure() -> None:
    prefix = test_cli_names_enforce_subcommand_structure.__name__

    class foo:

        @classmethod
        @atools.CLI()
        def bar(cls): ...

        @classmethod
        @atools.CLI()
        def baz(cls): ...

    @atools.CLI()
    def qux(): ...

    assert 'foo' in atools.CLI().make_argument_parser(test_cli_names_enforce_subcommand_structure).format_help()
    assert 'bar' in atools.CLI().make_argument_parser(foo)
    assert 'baz' in atools.CLI().make_argument_parser(foo)
    assert 'qux' in atools.CLI().make_argument_parser(test_cli_names_enforce_subcommand_structure).format_help()


def test_unresolved_annotation_raises_assertion_error() -> None:
    choices = ['a', 'b', 'c']

    with pytest.raises(AssertionError):
        @atools.CLI()
        def entrypoint(foo: 'typing.Annotated[str, atools.ArgumentParser.AddArgument[str](choices=choices)]') -> ...: ...

    def entrypoint(foo: 'typing.Annotated[str, atools.ArgumentParser.AddArgument[str](choices=choices)]') -> ...: ...
    entrypoint.__annotations__['foo'] = eval(entrypoint.__annotations__['foo'], globals(), locals())
    entrypoint = atools.CLI()(entrypoint)


def test_missing_entrypoint_generates_blank_entrypoint() -> None:
    assert '-h' in atools.CLI(test_missing_entrypoint_generates_blank_entrypoint.__name__).cli.format_help()


def test_var_positional_args_are_parsed() -> None:

    @atools.CLI()
    def entrypoint(*foo: int) -> dict[str, tuple[int, ...]]:
        return locals()

    assert entrypoint(shlex.split('1 2 3')) == {'foo': (1, 2, 3)}


def test_var_keyword_args_are_parsed() -> None:

    @atools.CLI()
    def entrypoint(**foo: int) -> dict[str, dict[str, int]]:
        return locals()

    assert entrypoint(shlex.split('--foo 1 --bar 2 --baz 3')) == {'foo': {'foo': 1, 'bar': 2, 'baz': 3}}
