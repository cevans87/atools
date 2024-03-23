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

    @atools.SQLiteCache(db_path=db_path)
    async def foo() -> None:
        nonlocal call_count
        call_count += 1

    await foo()
    await foo()
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


@pytest.mark.asyncio
async def test_method() -> None:
    call_count = 0

    class Foo:
        @atools.SQLiteCache(db_path='/home/modulo/atools/scratch/test.sqlite')
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


@pytest.mark.asyncio
async def test_classmethod() -> None:
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


@pytest.mark.asyncio
async def test_async_size_expires_memos() -> None:
    call_count = 0

    class Foo:

        @atools.SQLiteCache(size=1)
        async def foo(self, _) -> None:
            nonlocal call_count
            call_count += 1

    foo = Foo()
    await foo.foo(0)
    await foo.foo(1)
    await foo.foo(0)
    assert call_count == 3


@pytest.mark.asyncio
async def test_async_size_method_is_per_instance() -> None:
    call_count = 0

    class Foo:

        @atools.SQLiteCache(size=1)
        async def foo(self, _) -> None:
            nonlocal call_count
            call_count += 1

    class Bar(Foo):
        ...

    class Baz(Foo):
        ...

    await asyncio.gather((foo := Foo()).foo(0), (bar := Bar()).foo(0), (baz := Baz()).foo(0))
    assert call_count == 3
    await asyncio.gather(foo.foo(0), bar.foo(0), baz.foo(0))
    assert call_count == 3
    await asyncio.gather(foo.foo(1), bar.foo(1), baz.foo(1))
    assert call_count == 6
    await asyncio.gather(foo.foo(1), bar.foo(1), baz.foo(1))
    assert call_count == 6
    await asyncio.gather(foo.foo(0), bar.foo(0), baz.foo(0))
    assert call_count == 9
    await asyncio.gather(foo.foo(0), bar.foo(0), baz.foo(0))
    assert call_count == 9
    await asyncio.gather(Foo().foo(0), Bar().foo(0), Baz().foo(0))
    assert call_count == 12
    await asyncio.gather(Foo().foo(0), Bar().foo(0), Baz().foo(0))
    assert call_count == 15


@pytest.mark.asyncio
async def test_async_size_classmethod_is_per_class() -> None:
    call_count = 0

    class Foo:

        @classmethod
        @atools.SQLiteCache(size=1)
        async def foo(cls, _) -> None:
            nonlocal call_count
            call_count += 1

    class Bar(Foo):
        ...

    class Baz(Foo):
        ...

    await asyncio.gather((foo := Foo()).foo(0), (bar := Bar()).foo(0), (baz := Baz()).foo(0))
    assert call_count == 3
    await asyncio.gather(foo.foo(0), bar.foo(0), baz.foo(0))
    assert call_count == 3
    await asyncio.gather(foo.foo(1), bar.foo(1), baz.foo(1))
    assert call_count == 6
    await asyncio.gather(foo.foo(1), bar.foo(1), baz.foo(1))
    assert call_count == 6
    await asyncio.gather(foo.foo(0), bar.foo(0), baz.foo(0))
    assert call_count == 9
    await asyncio.gather(foo.foo(0), bar.foo(0), baz.foo(0))
    assert call_count == 9
    await asyncio.gather(Foo().foo(0), Bar().foo(0), Baz().foo(0))
    assert call_count == 9
    await asyncio.gather(Foo().foo(0), Bar().foo(0), Baz().foo(0))
    assert call_count == 9


@pytest.mark.asyncio
async def test_async_size_staticmethod_is_per_declaration() -> None:
    call_count = 0

    class Foo:

        @staticmethod
        @atools.SQLiteCache(size=1)
        async def foo(_) -> None:
            nonlocal call_count
            call_count += 1

    class Bar(Foo):
        ...

    class Baz(Foo):
        ...

    await asyncio.gather((foo := Foo()).foo(0), (bar := Bar()).foo(0), (baz := Baz()).foo(0))
    assert call_count == 1
    await asyncio.gather(foo.foo(0), bar.foo(0), baz.foo(0))
    assert call_count == 1
    await asyncio.gather(foo.foo(1), bar.foo(1), baz.foo(1))
    assert call_count == 2
    await asyncio.gather(foo.foo(1), bar.foo(1), baz.foo(1))
    assert call_count == 2
    await asyncio.gather(foo.foo(0), bar.foo(0), baz.foo(0))
    assert call_count == 3
    await asyncio.gather(foo.foo(0), bar.foo(0), baz.foo(0))
    assert call_count == 3
    await asyncio.gather(Foo().foo(0), Bar().foo(0), Baz().foo(0))
    assert call_count == 3
    await asyncio.gather(Foo().foo(0), Bar().foo(0), Baz().foo(0))
    assert call_count == 3


@pytest.mark.asyncio
async def test_herds_only_call_once() -> None:
    call_count = 0
    event = asyncio.Event()

    @atools.SQLiteCache()
    async def foo() -> None:
        nonlocal call_count
        await event.wait()
        call_count += 1

    futures = [asyncio.get_event_loop().create_task(foo()) for _ in range(10)]
    event.set()
    await asyncio.gather(*futures)

    assert call_count == 1


@pytest.mark.asyncio
async def test_exceptions_are_not_saved() -> None:
    call_count = 0

    class FooException(Exception):
        ...

    @atools.SQLiteCache()
    async def foo() -> None:
        nonlocal call_count
        call_count += 1
        raise FooException()

    with pytest.raises(FooException):
        await foo()
    assert call_count == 1

    with pytest.raises(FooException):
        await foo()
    assert call_count == 2
