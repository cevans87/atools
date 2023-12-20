from asyncio import (
    ensure_future, Event, gather, get_event_loop, new_event_loop, set_event_loop
)
from atools import memoize
import atools._memoize_decorator as test_module
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


@pytest.fixture
def prog() -> ModuleType:
    a_spec =  importlib.machinery.ModuleSpec()
    a = ModuleType('a', 'a docstring')
    a_b = ModuleType('a.b', 'a.b docstring')

    return a


def test_module_imports(prog: ModuleType) -> None:
    import a
    import a.b
