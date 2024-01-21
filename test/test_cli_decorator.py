import sys
from collections.abc import Generator
import importlib
import logging
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


def test_module_imports(blank: types.ModuleType) -> None:
    assert blank.__file__ == str(pathlib.Path(__file__).parent.absolute() / 'test_cli_modules' / 'blank' / 'blank.py')


def test_blank_has_no_children(blank: types.ModuleType) -> None:
    assert blank.main.decorations.parser._subparsers is None


def test_flag_types_has_children(flag_types: types.ModuleType) -> None:
    assert flag_types.main.decorations.parser._subparsers is not None


def test_blank_has_no_log_level_flag(blank: types.ModuleType) -> None:
    assert '--log-level' not in blank.main.decorations.parser.format_help()


def test_flag_types_has_log_level_flag(flag_types: types.ModuleType) -> None:
    assert '--log-level' in flag_types.main.decorations.parser.format_help()


def test_flag_types_parses_log_level(flag_types: types.ModuleType) -> None:
    args = flag_types.main.decorations.parser.parse_args(shlex.split('--log-level INFO'))
    assert args.log_level == logging.INFO

    args = flag_types.main.decorations.parser.parse_args(shlex.split('--log-level DEBUG'))
    assert args.log_level == logging.DEBUG


def test_flag_types_recieve_correct_arguments(flag_types: types.ModuleType) -> None:
    foo = flag_types.main.run(shlex.split('with_default'))
    assert flag_types.main.decorations.run(shlex.split('with_default')) == {
        'positional_only': 1,
        'positional_or_keyword': 2,
        'keyword_only': 3
    }

    for i in range(2):
        assert flag_types.main.decorations.run(shlex.split(f'without_default {i} {i + 1} --keyword-only {i + 2}')) == {
            'positional_only': i,
            'positional_or_keyword': i + 1,
            'keyword_only': i + 2,
        }

    assert flag_types.main.decorations.run(shlex.split('variadic 1 2 3 --kw0 foo bar --kw1 baz --kw2 qux quux')) == {
        'var_positional': []
    }


