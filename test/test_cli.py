import enum
import logging
import shlex
import types
import typing

import pydantic
import pytest

import atools


class FooEnum(enum.Enum):
    a = 1
    b = 2
    c = 3


class FooTuple(tuple):

    def __eq__(self, other) -> bool:
        return super().__eq__(other) and isinstance(other, type(self))


parameterize_args = pytest.mark.parametrize('arg,arg_t,default,expect', [
    ('42', int, 0, 42),
    ('3.14', float, 0.0, 3.14),
    ('True', bool, False, True),
    ('False', bool, True, False),
    ('Hi!', str, 'Bye!', 'Hi!'),
    ('None', None, None, None),
    ('None', types.NoneType, None, None),
    ('"[1, 2, 3, 4]"', list[int], [], [1, 2, 3, 4]),
    ('"(42, False, 3.14, \'Hi!\')"', tuple[int, bool, float, str], (0, True, 0.0, 'Bye!'), (42, False, 3.14, 'Hi!')),
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
    ('2', FooEnum, FooEnum.a, FooEnum.b),
    ('\'(42, \"hi!\", \"bye!\")\'', FooTuple[int, str, ...], FooTuple((0, 'Meh!',)), FooTuple((42, 'hi!', 'bye!'))),
    ('42', typing.Annotated[int, 'foo annotation'], 0, 42),
])


@parameterize_args
def test_parses_positional_only(arg, arg_t, default, expect) -> None:

    @atools.CLI()
    def entrypoint(foo: arg_t, /) -> dict[str, arg_t]:
        return locals()

    assert entrypoint.cli.run(shlex.split(arg)) == {'foo': expect}


@parameterize_args
def test_parses_positional_only_with_default(arg, arg_t, default, expect) -> None:

    @atools.CLI()
    def entrypoint(foo: arg_t = default, /) -> dict[str, arg_t]:
        return locals()

    assert entrypoint.cli.run([]) == {'foo': default}
    assert entrypoint.cli.run(shlex.split(arg)) == {'foo': expect}


@parameterize_args
def test_parses_positional_or_keyword(arg, arg_t, default, expect) -> None:

    @atools.CLI()
    def entrypoint(foo: arg_t) -> dict[str, arg_t]:
        return locals()

    with pytest.raises(SystemExit):
        entrypoint.cli.run([])
    assert entrypoint.cli.run(shlex.split(arg)) == {'foo': expect}


@parameterize_args
def test_parses_positional_or_keyword_with_default(arg, arg_t, default, expect) -> None:

    @atools.CLI()
    def entrypoint(foo: arg_t = default) -> dict[str, arg_t]:
        return locals()

    assert entrypoint.cli.run([]) == {'foo': default}
    assert entrypoint.cli.run(shlex.split(f'--foo {arg}')) == {'foo': expect}


@parameterize_args
def test_parses_keyword_only(arg, arg_t, default, expect) -> None:

    @atools.CLI()
    def entrypoint(*, foo: arg_t) -> dict[str, arg_t]:
        return locals()

    with pytest.raises(SystemExit):
        assert entrypoint.cli.run([])
    assert entrypoint.cli.run(shlex.split(f'--foo {arg}')) == {'foo': expect}


@parameterize_args
def test_parses_keyword_only_with_default(arg, arg_t, default, expect) -> None:

    @atools.CLI()
    def entrypoint(*, foo: arg_t = default) -> dict[str, arg_t]:
        return locals()

    assert entrypoint.cli.run([]) == {'foo': default}
    assert entrypoint.cli.run(shlex.split(f'--foo {arg}')) == {'foo': expect}


def test_execute_hidden_subcommand_works() -> None:

    @atools.CLI(f'{test_execute_hidden_subcommand_works.__name__}._foo')
    def _foo(foo: str) -> dict[str, str]:
        return locals()

    assert '_foo' not in atools.CLI(f'{test_execute_hidden_subcommand_works.__name__}').parser.format_help()
    assert atools.CLI(f'{test_execute_hidden_subcommand_works.__name__}').run(shlex.split(
        '_foo hidden_subcommand_works'
    )) == {'foo': 'hidden_subcommand_works'}


def test_async_entrypoint_works() -> None:

    @atools.CLI()
    async def entrypoint(foo: int) -> dict[str, int]:
        return locals()

    assert entrypoint.cli.run(shlex.split('42')) == {'foo': 42}


def test_dash_help_prints_parameter_annotation() -> None:
    @atools.CLI()
    def entrypoint(
        foo: typing.Annotated[int, 'This is my comment.']
    ) -> dict[str, int]: ...

    assert 'This is my comment.' in entrypoint.cli.parser.format_help()


def test_positional_only_without_default_works() -> None:
    @atools.CLI()
    def entrypoint(
        foo: typing.Annotated[int, 'Help text for foo.'],
        /,
    ) -> dict[str, int]:
        return locals()

    with pytest.raises(SystemExit):
        entrypoint.cli.run(shlex.split(''))
    assert entrypoint.cli.run(shlex.split('42')) == {'foo': 42}


def test_dash_help_prints_entrypoint_doc() -> None:
    @atools.CLI()
    def entrypoint(
        foo: int,
    ) -> dict[str, int]:
        """What's up, Doc?"""

    assert """What's up, Doc?""" in entrypoint.cli.parser.format_help()


def test_annotation_log_level_of_logger_sets_choices() -> None:
    logger = logging.getLogger('test_annotated_of_logger_sets_choices')

    @atools.CLI()
    def entrypoint(
        foo: typing.Annotated[
            atools.CLI.LogLevelLiteral,
            atools.CLI.Annotation[atools.CLI.LogLevelLiteral].log_level_with_logger(logger),
        ] = 'DEBUG'
    ) -> dict[str, pydantic.PositiveInt]: ...

    for choice in logging.getLevelNamesMapping().keys():
        assert choice in entrypoint.cli.parser.format_help()


def test_annotation_log_level_of_logger_sets_log_level() -> None:
    logger = logging.getLogger('test_annotation_log_level_of_logger_sets_log_level')
    logger.setLevel(logging.ERROR)

    @atools.CLI()
    def entrypoint(
        foo: typing.Annotated[
            atools.CLI.LogLevelLiteral,
            atools.CLI.Annotation[atools.CLI.LogLevelLiteral].log_level_with_logger(logger),
        ] = 'DEBUG'
    ) -> dict[str, atools.CLI.LogLevelLiteral]:
        return locals()

    assert logger.level == logging.ERROR

    assert entrypoint.cli.run(shlex.split('--foo INFO')) == {'foo': 'INFO'}
    assert logger.level == logging.INFO

    assert entrypoint.cli.run(shlex.split('')) == {'foo': 'DEBUG'}
    assert logger.level == logging.DEBUG


def test_annotation_with_count_action_counts() -> None:
    @atools.CLI()
    def entrypoint(
        foo: typing.Annotated[
            pydantic.NonNegativeInt,
            atools.CLI.Annotation[pydantic.NonNegativeInt](name_or_flags=['-f', '--foo'], action='count'),
        ] = 0,
    ) -> dict[str, int]:
        return locals()

    assert entrypoint.cli.run(shlex.split('')) == {'foo': 0}
    assert entrypoint.cli.run(shlex.split('--foo')) == {'foo': 1}
    assert entrypoint.cli.run(shlex.split('--foo --foo')) == {'foo': 2}
    assert entrypoint.cli.run(shlex.split('-f --foo')) == {'foo': 2}
    assert entrypoint.cli.run(shlex.split('-ff')) == {'foo': 2}


def test_cli_names_enforce_subcommand_structure() -> None:

    for name in ['foo.baz', 'foo.qux', 'bar.quux', 'bar.corge']:
        @atools.CLI(name)
        def entrypoint(foo: int) -> dict[str, object]:
            return locals()

    assert 'foo' in atools.CLI().parser.format_help()
    assert 'bar' in atools.CLI().parser.format_help()
    assert 'baz' in atools.CLI('foo').parser.format_help()
    assert 'qux' in atools.CLI('foo').parser.format_help()
    assert 'quux' in atools.CLI('bar').parser.format_help()
    assert 'corge' in atools.CLI('bar').parser.format_help()


def test_unresolved_annotation_raises_runtime_error() -> None:
    choices = ['a', 'b', 'c']

    @atools.CLI()
    def entrypoint(foo: 'typing.Annotated[str, atools.CLI.Annotation[str](choices=choices)]') -> ...: ...

    with pytest.raises(RuntimeError):
        entrypoint.cli.run(shlex.split('a'))

    entrypoint.__annotations__['foo'] = eval(entrypoint.__annotations__['foo'], globals(), locals())
    entrypoint.cli.run(shlex.split('a'))


def test_missing_entrypoint_generates_blank_entrypoint() -> None:
    assert '-h' in atools.CLI('foobar').parser.format_help()


def test_var_positional_args_are_parsed() -> None:

    @atools.CLI()
    def entrypoint(*foo: int) -> dict[str, tuple[int, ...]]:
        return locals()

    assert entrypoint.cli.run(shlex.split('1 2 3')) == {'foo': (1, 2, 3)}


def test_var_keyword_args_are_parsed() -> None:

    @atools.CLI()
    def entrypoint(**foo: int) -> dict[str, dict[str, int]]:
        return locals()

    assert entrypoint.cli.run(shlex.split('--foo 1 --bar 2 --baz 3')) == {'foo': {'foo': 1, 'bar': 2, 'baz': 3}}


def test_parses_enum() -> None:

    class Foo(enum.StrEnum):
        bar = 'bar'
        baz = 'baz'

    @atools.CLI()
    def entrypoint(foo: Foo, bar: Foo) -> dict[str, Foo]:
        return locals()

    assert entrypoint.cli.run(shlex.split('\'"bar"\' \'"baz"\'')) == {'foo': Foo.bar, 'bar': Foo.baz}
