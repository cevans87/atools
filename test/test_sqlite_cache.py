import asyncio
import inspect
import tempfile

import pytest

import atools

module = inspect.getmodule(atools.SQLiteCache)

# TODO: Multi tests are missing. This suite heavily relies upon determining whether coroutines are running vs suspended
#  (via asyncio.eager_task_factory). Ideally, similar functionality exists for threading. Otherwise, we need to find a
#  way to determine that thread execution has reached a certain point. Ideally without mocking synchronization
#  primitives.


@pytest.fixture(autouse=True)
def event_loop() -> asyncio.AbstractEventLoop:
    """All async tests execute eagerly.

    Upon task creation return, we can be sure that the task has gotten to a point that it is either blocked or done.
    """

    eager_loop = asyncio.new_event_loop()
    eager_loop.set_task_factory(asyncio.eager_task_factory)
    yield eager_loop
    eager_loop.close()


@pytest.fixture
def db_path() -> str:
    with tempfile.NamedTemporaryFile() as f:
        yield f.name


@pytest.mark.asyncio
async def test_async_zero_args(db_path: str) -> None:
    call_count = 0

    @atools.SQLiteCache()
    async def foo() -> None:
        nonlocal call_count
        call_count += 1

    await foo()
    await foo()
    assert call_count == 1


def test_multi_zero_args(db_path: str) -> None:
    call_count = 0

    @atools.SQLiteCache()
    def foo() -> None:
        nonlocal call_count
        call_count += 1

    foo()
    foo()
    assert call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('arg', [None, 1, 'foo', 0.0])
async def test_async_primitive_arg(db_path, arg) -> None:
    call_count = 0

    @atools.SQLiteCache(db_path=db_path)
    async def foo(_) -> None:
        nonlocal call_count
        call_count += 1

    await foo(arg)
    await foo(arg)
    assert call_count == 1


@pytest.mark.parametrize('arg', [None, 1, 'foo', 0.0])
def test_multi_primitive_arg(db_path, arg) -> None:
    call_count = 0

    @atools.SQLiteCache(db_path=db_path)
    def foo(_) -> None:
        nonlocal call_count
        call_count += 1

    foo(arg)
    foo(arg)
    assert call_count == 1


@pytest.mark.asyncio
async def test_async_method() -> None:
    call_count = 0

    class Foo:
        @atools.SQLiteCache()
        async def foo(self) -> None:
            nonlocal call_count
            call_count += 1

    foo0, foo1 = Foo(), Foo()
    await foo0.foo()
    await foo0.foo()
    assert call_count == 1

    await foo1.foo()
    await foo1.foo()
    assert call_count == 2


def test_multi_method() -> None:
    call_count = 0

    class Foo:
        @atools.SQLiteCache()
        def foo(self) -> None:
            nonlocal call_count
            call_count += 1

    foo0, foo1 = Foo(), Foo()
    foo0.foo()
    foo0.foo()
    assert call_count == 1

    foo1.foo()
    foo1.foo()
    assert call_count == 2


@pytest.mark.asyncio
async def test_async_classmethod() -> None:
    call_count = 0

    class Foo:
        @classmethod
        @atools.SQLiteCache()
        async def foo(cls) -> None:
            nonlocal call_count
            call_count += 1

    foo0, foo1 = Foo(), Foo()
    await foo0.foo()
    await foo0.foo()
    assert call_count == 1

    await foo1.foo()
    await foo1.foo()
    assert call_count == 1

    await Foo.foo()
    await Foo.foo()
    assert call_count == 1


def test_multi_classmethod() -> None:
    call_count = 0

    class Foo:
        @classmethod
        @atools.SQLiteCache()
        def foo(cls) -> None:
            nonlocal call_count
            call_count += 1

    foo0, foo1 = Foo(), Foo()
    foo0.foo()
    foo0.foo()
    assert call_count == 1

    foo1.foo()
    foo1.foo()
    assert call_count == 1

    Foo.foo()
    Foo.foo()
    assert call_count == 1


@pytest.mark.asyncio
async def test_async_staticmethod() -> None:
    call_count = 0

    class Foo:
        @staticmethod
        @atools.SQLiteCache()
        async def foo() -> None:
            nonlocal call_count
            call_count += 1

    foo0, foo1 = Foo(), Foo()
    await foo0.foo()
    await foo0.foo()
    assert call_count == 1

    await foo1.foo()
    await foo1.foo()
    assert call_count == 1

    await Foo.foo()
    await Foo.foo()
    assert call_count == 1


def test_multi_staticmethod() -> None:
    call_count = 0

    class Foo:
        @staticmethod
        @atools.SQLiteCache()
        def foo() -> None:
            nonlocal call_count
            call_count += 1

    foo0, foo1 = Foo(), Foo()
    foo0.foo()
    foo0.foo()
    assert call_count == 1

    foo1.foo()
    foo1.foo()
    assert call_count == 1

    Foo.foo()
    Foo.foo()
    assert call_count == 1


