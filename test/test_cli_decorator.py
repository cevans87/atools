import sys
from collections.abc import Generator
import importlib
import pathlib
import pytest
import shlex
import types


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
def async_entrypoint() -> Generator[types.ModuleType, None, None]:
    yield from module('async_entrypoint')


def test_module_imports(blank: types.ModuleType) -> None:
    assert blank.__file__ == str(pathlib.Path(__file__).parent.absolute() / 'test_cli_modules' / 'blank' / 'blank.py')


def test_blank_has_no_children(blank: types.ModuleType) -> None:
    assert blank.entrypoint.cli.parser._subparsers is None


def test_flag_types_has_children(flag_types: types.ModuleType) -> None:
    assert flag_types.entrypoint.cli.parser._subparsers is not None


def test_flag_types_receive_correct_arguments(flag_types: types.ModuleType) -> None:
    assert flag_types.entrypoint.cli.run(shlex.split('. 1')) == {'foo': 1}
    assert flag_types.entrypoint.cli.run(shlex.split('. 2')) == {'foo': 2}


def test_flag_types_with_default_receive_correct_arguments(flag_types: types.ModuleType) -> None:
    assert flag_types.entrypoint.cli.run(shlex.split(
        'with_default'
    )) == {
        'positional_only_with_default': 0,
        'positional_or_keyword_with_default': 1,
        'keyword_only_with_default': 2,
    }
    assert flag_types.entrypoint.cli.run(shlex.split(
        'with_default 2001 --positional-or-keyword-with-default 2049 --keyword-only-with-default 2077'
    )) == {
        'positional_only_with_default': 2001,
        'positional_or_keyword_with_default': 2049,
        'keyword_only_with_default': 2077,
    }


def test_flag_types_without_default_receive_correct_arguments(flag_types: types.ModuleType) -> None:
    assert flag_types.entrypoint.cli.run(shlex.split(
        f'without_default 1 2 --keyword-only 3'
    )) == {
        'positional_only': 1,
        'positional_or_keyword': 2,
        'keyword_only': 3,
    }


def test_variadic_is_unsupported() -> None:
    with pytest.raises(RuntimeError):
        next(module('variadic'))


def test_hidden_subcommand_does_not_show_subcommand(hidden_subcommand: types.ModuleType) -> None:
    assert '_should_not_show' not in hidden_subcommand.entrypoint.cli.parser.format_help()


def test_hidden_subcommand_parses_hidden_subcommand(hidden_subcommand: types.ModuleType) -> None:
    assert hidden_subcommand.entrypoint.cli.run(shlex.split(
        f'_should_not_show hidden_subcommand_works'
    )) == {
        'foo': 'hidden_subcommand_works',
    }


def test_async_entrypoint_works(async_entrypoint: types.ModuleType) -> None:
    assert async_entrypoint.entrypoint.cli.run(shlex.split(
        '42'
    )) == {
        'answer': 42
    }
