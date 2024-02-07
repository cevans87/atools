import collections.abc
import enum
import importlib
import logging
import pathlib
import shlex
import types
import typing
import sys

import pydantic
import pytest

import atools


def module(name: str) -> collections.abc.Generator[types.ModuleType, None, None]:
    sys.path.insert(0, str(pathlib.Path(__file__).parent.absolute() / 'test_cli_modules' / name))
    yield importlib.import_module(name)
    sys.path.pop(0)


@pytest.fixture
def blank() -> types.ModuleType:
    return importlib.import_module('.test_cli_modules.blank.blank', package=__package__)


@pytest.fixture
def flag_types() -> types.ModuleType:
    importlib.import_module('.test_cli_modules.flag_types.flag_types.with_default', package=__package__)
    return importlib.import_module('.test_cli_modules.flag_types.flag_types', package=__package__)


@pytest.fixture
def hidden_subcommand() -> types.ModuleType:
    importlib.import_module(
        '.test_cli_modules.hidden_subcommand.hidden_subcommand._should_not_show', package=__package__
    )
    return importlib.import_module('.test_cli_modules.hidden_subcommand.hidden_subcommand', package=__package__)


@pytest.fixture
def no_submodules() -> types.ModuleType:
    return importlib.import_module('.test_cli_modules.no_submodules.no_submodules', package=__package__)


def test_flag_types_with_default_receive_correct_arguments() -> None:
    @atools.CLI()
    def entrypoint(
        positional_only_with_default: int = 0,
        /,
        positional_or_keyword_with_default: int = 1,
        *,
        keyword_only_with_default: int = 2
    ) -> dict[str, int]:
        return locals()

    assert entrypoint.cli.run(shlex.split(
        ''
    )) == {
        'positional_only_with_default': 0,
        'positional_or_keyword_with_default': 1,
        'keyword_only_with_default': 2,
    }
    assert entrypoint.cli.run(shlex.split(
        '2001 --positional-or-keyword-with-default 2049 --keyword-only-with-default 2077'
    )) == {
        'positional_only_with_default': 2001,
        'positional_or_keyword_with_default': 2049,
        'keyword_only_with_default': 2077,
    }


def test_flag_types_without_default_receive_correct_arguments() -> None:
    @atools.CLI()
    def entrypoint(
        positional_only: int,
        /,
        positional_or_keyword: int,
        *,
        keyword_only: int
    ) -> dict[str, int]:
        return locals()

    assert entrypoint.cli.run(shlex.split(
        f'1 2 --keyword-only 3'
    )) == {
        'positional_only': 1,
        'positional_or_keyword': 2,
        'keyword_only': 3,
    }
    with pytest.raises(SystemExit):
        entrypoint.cli.run(shlex.split(f'1 2'))
    with pytest.raises(SystemExit):
        entrypoint.cli.run(shlex.split(f'1 --keyword-only 3'))


def test_dash_help_does_not_show_hidden_subcommand(hidden_subcommand: types.ModuleType) -> None:
    assert '_should_not_show' not in atools.CLI(hidden_subcommand.__name__).parser.format_help()


def test_execute_hidden_subcommand_works(hidden_subcommand: types.ModuleType) -> None:
    assert atools.CLI(hidden_subcommand.__name__).run(shlex.split(
        f'_should_not_show entrypoint hidden_subcommand_works'
    )) == {
        'foo': 'hidden_subcommand_works',
    }


def test_async_entrypoint_works() -> None:

    @atools.CLI()
    async def entrypoint(foo: int) -> dict[str, int]:
        return locals()

    assert entrypoint.cli.run(shlex.split('42')) == {'foo': 42}


def test_no_submodules_does_not_include_submodules(no_submodules: types.ModuleType) -> None:
    assert 'should_not_be_included' not in atools.CLI(no_submodules.__name__).parser.format_help()


def test_parses_bool_parameter() -> None:
    @atools.CLI()
    def entrypoint(foo: bool) -> dict[str, bool]:
        return locals()

    assert entrypoint.cli.run(shlex.split('True')) == {'foo': True}
    assert entrypoint.cli.run(shlex.split('False')) == {'foo': False}


def test_parses_float_parameter() -> None:
    @atools.CLI()
    def entrypoint(foo: float) -> dict[str, float]:
        return locals()

    assert entrypoint.cli.run(shlex.split('3.14')) == {'foo': 3.14}


def test_parses_int_parameter() -> None:
    @atools.CLI()
    def entrypoint(foo: int) -> dict[str, int]:
        return locals()

    assert entrypoint.cli.run(shlex.split('42')) == {'foo': 42}


def test_parses_str_parameter() -> None:
    @atools.CLI()
    def entrypoint(foo: str) -> dict[str, str]:
        return locals()

    assert entrypoint.cli.run(shlex.split('hi!')) == {'foo': 'hi!'}


def test_parses_none_parameter() -> None:
    @atools.CLI()
    def entrypoint(foo: None) -> dict[str, str]:
        return locals()

    assert entrypoint.cli.run(shlex.split('None')) == {'foo': None}


def test_parses_typing_union_parameter() -> None:
    @atools.CLI()
    def entrypoint(foo: typing.Union[int, float]) -> dict[str, typing.Union[int, float]]:
        return locals()

    assert entrypoint.cli.run(shlex.split('42')) == {'foo': 42}
    assert entrypoint.cli.run(shlex.split('3.14')) == {'foo': 3.14}


def test_parses_types_union_type_parameter() -> None:
    @atools.CLI()
    def entrypoint(foo: int | float) -> dict[str, int | float]:
        return locals()

    assert entrypoint.cli.run(shlex.split('42')) == {'foo': 42}
    assert entrypoint.cli.run(shlex.split('3.14')) == {'foo': 3.14}


def test_parses_typing_optional_parameter() -> None:
    @atools.CLI()
    def entrypoint(foo: typing.Optional[int]) -> dict[str, typing.Optional[int]]:
        return locals()

    assert entrypoint.cli.run(shlex.split('42')) == {'foo': 42}
    assert entrypoint.cli.run(shlex.split('None')) == {'foo': None}


def test_parses_dict_parameter() -> None:
    @atools.CLI()
    def entrypoint(foo: dict[bool, float]) -> dict[str, dict[bool, float]]:
        return locals()

    assert entrypoint.cli.run(shlex.split('"{True: 2.0}"')) == {'foo': {True: 2.0}}
    with (pytest.raises(RuntimeError)):
        entrypoint.cli.run(shlex.split('"{42: 2.0}"'))
    with (pytest.raises(RuntimeError)):
        entrypoint.cli.run(shlex.split('"{True: \'the answer!\'}"'))

    @atools.CLI()
    def entrypoint(foo: dict[int, str]) -> dict[str, dict[int, str]]:
        return locals()

    assert entrypoint.cli.run(shlex.split('"{42: \'the answer!\'}"')) == {'foo': {42: 'the answer!'}}
    with (pytest.raises(RuntimeError)):
        entrypoint.cli.run(shlex.split('"{True: \'the answer!\'}"'))
    with (pytest.raises(RuntimeError)):
        entrypoint.cli.run(shlex.split('"{42: 2.0}"'))


def test_parses_dict_of_dict_parameter() -> None:
    @atools.CLI()
    def entrypoint(foo: dict[bool, dict[float, dict[int, str]]]) -> dict[str, dict[bool, dict[float, dict[int, str]]]]:
        return locals()

    assert entrypoint.cli.run(shlex.split('"{True: {4.0: {42: \'yes!\'}}}"')) == {'foo': {True: {4.0: {42: 'yes!'}}}}
    with pytest.raises(RuntimeError):
        entrypoint.cli.run(shlex.split('"{True: {4.0: {42: False}}}"'))


def test_parses_frozenset_parameter() -> None:
    @atools.CLI()
    def entrypoint(foo: frozenset[int]) -> dict[str, frozenset[int]]:
        return locals()

    assert entrypoint.cli.run(shlex.split(
        '\'{1, 2, 3, 4}\''
    )) == {
        'foo': frozenset({1, 2, 3, 4})
    }


def test_parses_list_parameter() -> None:
    @atools.CLI()
    def entrypoint(foo: list[int]) -> dict[str, list[int]]:
        return locals()

    assert entrypoint.cli.run(shlex.split(
        '\'[1, 2, 3, 4]\''
    )) == {
        'foo': [1, 2, 3, 4],
    } != {
        'foo': (1, 2, 3, 4)
    }


def test_parses_set_parameter() -> None:
    @atools.CLI()
    def entrypoint(foo: set[int]) -> dict[str, set[int]]:
        return locals()

    assert entrypoint.cli.run(shlex.split('\'{1, 2, 3, 4}\'')) == {'foo': {1, 2, 3, 4}}


def test_parses_tuple_parameter() -> None:
    @atools.CLI()
    def entrypoint(foo: tuple[bool, float, int, str]) -> dict[str, tuple[bool, float, int, str]]:
        return locals()

    assert entrypoint.cli.run(shlex.split('\'(True, 3.14, 42, \"hi!\")\'')) == {'foo': (True, 3.14, 42, 'hi!')}


def test_parses_tuple_with_variable_length_parameter() -> None:
    @atools.CLI()
    def entrypoint(foo: tuple[int, ...]) -> dict[str, tuple[int, ...]]:
        return locals()

    assert entrypoint.cli.run(shlex.split('\'(1, 2, 3, 4)\'')) == {'foo': (1, 2, 3, 4)}

    @atools.CLI()
    def entrypoint(foo: tuple[str, int, ...]) -> dict[str, tuple[str, int, ...]]:
        return locals()

    assert entrypoint.cli.run(shlex.split('\'(\"hi!\", 1, 2, 3, 4)\'')) == {'foo': ('hi!', 1, 2, 3, 4)}


def test_parses_enum_type_parameter() -> None:

    class Foo(enum.Enum):
        a = 1
        b = 2
        c = 3

    @atools.CLI()
    def entrypoint(foo: Foo) -> dict[str, Foo]:
        return locals()

    assert entrypoint.cli.run(shlex.split('1')) == {'foo': Foo.a}


def test_parses_custom_primitive_type_parameter() -> None:

    class Foo(str):

        def __eq__(self, other) -> bool:
            return super().__eq__(other) and isinstance(other, type(self))

    @atools.CLI()
    def entrypoint(foo: Foo) -> dict[str, Foo]:
        return locals()

    assert entrypoint.cli.run(shlex.split('\\\'haha\\\'')) == {'foo': Foo('haha')} != {'foo': 'haha'}


def test_parses_custom_container_type_parameter() -> None:
    class Foo(tuple):

        def __eq__(self, other) -> bool:
            return super().__eq__(other) and isinstance(other, type(self))

    @atools.CLI()
    def entrypoint(foo: Foo[bool, float, int, str, ...]) -> dict[str, Foo[bool, float, int, str, ...]]:
        return locals()

    assert entrypoint.cli.run(shlex.split(
        '\'(False, 3.14, 42, \"hi!\", \"bye!\")\''
    )) == {
        'foo': Foo((False, 3.14, 42, 'hi!', 'bye!')),
    } != {
        'foo': tuple((False, 3.14, 42, 'hi!', 'bye!'))
    }


def test_parses_annotated_int() -> None:
    @atools.CLI()
    def entrypoint(
        foo: typing.Annotated[int, 'This is my annotation']
    ) -> dict[str, int]:
        return locals()

    assert entrypoint.cli.run(shlex.split('42')) == {'foo': 42}


def test_dash_help_prints_parameter_annotation() -> None:
    @atools.CLI()
    def entrypoint(
        foo: typing.Annotated[int, 'This is my comment.']
    ) -> dict[str, int]:
        """"""

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


def test_positional_only_with_default_works() -> None:
    @atools.CLI()
    def entrypoint(
        foo: typing.Annotated[int, 'Help text for foo.'] = 0,
        /,
    ) -> dict[str, int]:
        return locals()

    assert entrypoint.cli.run(shlex.split('')) == {'foo': 0}
    assert entrypoint.cli.run(shlex.split('42')) == {'foo': 42}


def test_positional_or_keyword_without_default_works() -> None:
    @atools.CLI()
    def entrypoint(
        foo: typing.Annotated[int, 'Help text for foo.'],
    ) -> dict[str, int]:
        return locals()

    with pytest.raises(SystemExit):
        entrypoint.cli.run(shlex.split(''))
    assert entrypoint.cli.run(shlex.split('42')) == {'foo': 42}


def test_positional_or_keyword_with_default_works() -> None:
    @atools.CLI()
    def entrypoint(
        foo: typing.Annotated[int, 'Help text for foo.'] = 0,
    ) -> dict[str, int]:
        return locals()

    assert entrypoint.cli.run(shlex.split('')) == {'foo': 0}
    assert entrypoint.cli.run(shlex.split('--foo 42')) == {'foo': 42}


def test_keyword_only_without_default_works() -> None:
    @atools.CLI()
    def entrypoint(
        *,
        foo: typing.Annotated[int, 'Help text for foo.'],
    ) -> dict[str, int]:
        return locals()

    with pytest.raises(SystemExit):
        entrypoint.cli.run(shlex.split(''))
    assert entrypoint.cli.run(shlex.split('--foo 42')) == {'foo': 42}


def test_keyword_only_with_default_works() -> None:
    @atools.CLI()
    def entrypoint(
        *,
        foo: typing.Annotated[int, 'Help text for foo.'] = 0,
    ) -> dict[str, int]:
        return locals()

    assert entrypoint.cli.run(shlex.split('')) == {'foo': 0}
    assert entrypoint.cli.run(shlex.split('--foo 42')) == {'foo': 42}


def test_var_positional_does_not_work() -> None:
    @atools.CLI()
    def entrypoint(*foo: int) -> dict[str, tuple[int, ...]]: ...

    with pytest.raises(RuntimeError):
        getattr(entrypoint.cli, 'parser')


def test_var_keyword_does_not_work() -> None:
    @atools.CLI()
    def entrypoint(**foo: int) -> dict[str, dict[str, int]]: ...

    with pytest.raises(RuntimeError):
        getattr(entrypoint.cli, 'parser')


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
