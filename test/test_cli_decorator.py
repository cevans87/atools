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
    assert blank.main.cli.parser._subparsers is None


def test_flag_types_has_children(flag_types: types.ModuleType) -> None:
    assert flag_types.main.cli.parser._subparsers is not None


def test_blank_has_no_log_level_flag(blank: types.ModuleType) -> None:
    assert '--log-level' not in blank.main.cli.parser.format_help()


def test_flag_types_has_log_level_flag(flag_types: types.ModuleType) -> None:
    assert '--log-level' in flag_types.main.cli.parser.format_help()


def test_flag_types_parses_log_level(flag_types: types.ModuleType) -> None:
    args = flag_types.main.cli.parser.parse_args(shlex.split('. --log-level INFO 1'))
    assert args.log_level == logging.INFO

    args = flag_types.main.cli.parser.parse_args(shlex.split('. --log-level DEBUG 1'))
    assert args.log_level == logging.DEBUG


def test_flag_types_recieve_correct_arguments(flag_types: types.ModuleType) -> None:
    assert flag_types.main.cli.run(shlex.split('. 1')) == {'foo': 1}
    assert flag_types.main.cli.run(shlex.split('. 2')) == {'foo': 2}
    assert flag_types.main.cli.run(shlex.split(
        'with_default'
    )) == {
        'positional_only_with_default': 0,
        'positional_or_keyword_with_default': 1,
        'keyword_only_with_default': 2,
    }
    assert flag_types.main.cli.run(shlex.split(
        'with_default 1 --positional-or-keyword-with-default 2 --keyword-only-with-default 3'
    )) == {
        'positional_only_with_default': 1,
        'positional_or_keyword_with_default': 2,
        'keyword_only_with_default': 3,
    }

    #for i in range(2):
    #    assert flag_types.main.cli.run(shlex.split(f'without_default {i} {i + 1} --keyword-only {i + 2}')) == {
    #        'positional_only': i,
    #        'positional_or_keyword': i + 1,
    #        'keyword_only': i + 2,
    #    }

    #assert flag_types.main.cli.run(shlex.split('variadic 1 2 3 --kw0 foo bar --kw1 baz --kw2 qux quux')) == {
    #    'var_positional': [],
    #    'var_keyword': {},
    #}


