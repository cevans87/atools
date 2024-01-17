import sys
from asyncio import (
    ensure_future, Event, gather, get_event_loop, new_event_loop, set_event_loop
)
from atools import memoize
import atools._memoize_decorator as test_module
from collections.abc import Generator
from datetime import timedelta
import importlib
from pathlib import Path, PosixPath
import pytest
from sqlite3 import connect
from tempfile import NamedTemporaryFile
from types import ModuleType
from typing import Callable, FrozenSet, Hashable, Iterable, Tuple
from unittest.mock import call, MagicMock, patch
from weakref import ref
from importlib import import_module


sys.path.insert(0, str(Path(__file__).parent.absolute() / 'test_cli_modules'))


@pytest.fixture
def blank() -> Generator[ModuleType, None, None]:
    yield import_module('blank')


@pytest.fixture
def one_child() -> Generator[ModuleType, None, None]:
    yield import_module('one_child')


def test_module_imports(blank: ModuleType) -> None:
    assert blank.__file__ == str(Path(__file__).parent.absolute() / 'test_cli_modules' / 'blank' / '__init__.py')


def test_blank_has_no_children(blank: ModuleType) -> None:
    parser = cli(blank)
