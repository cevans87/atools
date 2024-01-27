from collections.abc import Generator
import importlib
import pathlib
import pytest
import shlex
import types
import typing
import sys

import atools


def module(name: str) -> Generator[types.ModuleType, None, None]:
    sys.path.insert(0, str(pathlib.Path(__file__).parent.absolute() / 'test_cli_modules' / name))
    yield importlib.import_module(name)
    sys.path.pop(0)


@pytest.fixture
def blank() -> Generator[types.ModuleType, None, None]:
    yield from module('blank')


@pytest.fixture
def flag_types() -> Generator[types.ModuleType, None, None]:
    yield from module('flag_types')


@pytest.fixture
def hidden_subcommand() -> Generator[types.ModuleType, None, None]:
    yield from module('hidden_subcommand')


@pytest.fixture
def no_submodules() -> Generator[types.ModuleType, None, None]:
    yield from module('no_submodules')


def test_blank_parser_has_no_children(blank: types.ModuleType) -> None:
    assert blank.entrypoint.cli._parser._subparsers is None


def test_flag_types_parser_has_children(flag_types: types.ModuleType) -> None:
    assert flag_types.entrypoint.cli._parser._subparsers is not None


def test_flag_types_init_run_receives_correct_arguments(flag_types: types.ModuleType) -> None:
    assert flag_types.entrypoint.cli.run(shlex.split('. 1')) == {'foo': 1}
    assert flag_types.entrypoint.cli.run(shlex.split('. 2')) == {'foo': 2}


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


def test_variadic_is_unsupported() -> None:
    with pytest.raises(RuntimeError):
        next(module('variadic'))


def test_dash_help_does_not_show_hidden_subcommand(hidden_subcommand: types.ModuleType) -> None:
    assert '_should_not_show' not in hidden_subcommand.entrypoint.cli._parser.format_help()


def test_execute_hidden_subcommand_works(hidden_subcommand: types.ModuleType) -> None:
    assert hidden_subcommand.entrypoint.cli.run(shlex.split(
        f'_should_not_show hidden_subcommand_works'
    )) == {
        'foo': 'hidden_subcommand_works',
    }


def test_async_entrypoint_works() -> None:

    @atools.CLI()
    async def entrypoint(foo: int) -> dict[str, int]:
        return locals()

    assert entrypoint.cli.run(shlex.split('42')) == {'foo': 42}


def test_no_submodules_does_not_include_submodules(no_submodules: types.ModuleType) -> None:
    assert 'should_not_be_included' not in no_submodules.entrypoint.cli._parser.format_help()


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
        'foo': [1, 2, 3, 4]
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


def test_parses_custom_primitive_type_parameter() -> None:

    class Foo(str):

        def __eq__(self, other) -> bool:
            return super().__eq__(other) and isinstance(other, type(self))

    @atools.CLI()
    def entrypoint(foo: Foo) -> dict[str, Foo]:
        return locals()

    assert entrypoint.cli.run(shlex.split(
        '\\\'haha\\\''
    )) == {
        'foo': Foo('haha')
    } != {
        'foo': 'haha'
    }


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
        'foo': tuple((False, 3.14, 42, 'hi!', 'bye!')),
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
        foo: typing.Annotated[int, 'This is my annotation.']
    ) -> dict[str, int]:
        return locals()

    assert 'This is my annotation.' in entrypoint.cli._parser.format_help()


def test_dash_help_prints_entrypoint_doc() -> None:
    @atools.CLI()
    def entrypoint(
        foo: typing.Annotated[int, 'This is my annotation.']
    ) -> dict[str, int]:
        """What's up, Doc?"""
        return locals()

    assert """What's up, Doc?""" in entrypoint.cli._parser.format_help()
