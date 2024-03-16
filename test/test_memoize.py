import asyncio

import pytest

import atools

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


@pytest.mark.asyncio
async def test_async_zero_args() -> None:
    call_count = 0

    @atools.Memoize()
    async def foo() -> None:
        nonlocal call_count
        call_count += 1

    await foo()
    await foo()
    assert call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('arg', [None, 1, 'foo', 0.0])
async def test_async_primitive_arg(arg) -> None:
    call_count = 0

    @atools.Memoize()
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
        @atools.Memoize()
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
        @atools.Memoize()
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

        @atools.Memoize(size=1)
        async def foo(self, _) -> None:
            nonlocal call_count
            call_count += 1

    foo = Foo()
    await foo.foo(0)
    await foo.foo(1)
    await foo.foo(0)
    assert call_count == 3


@pytest.mark.asyncio
async def test_async_size_on_methods_has_size_per_bound_instance() -> None:
    call_count = 0

    class Foo:

        @atools.Memoize(size=1)
        async def foo(self, _) -> None:
            nonlocal call_count
            call_count += 1

    foo0, foo1 = Foo(), Foo()
    await foo0.foo(0)
    assert call_count == 1
    await foo1.foo(0)
    assert call_count == 2
    await foo0.foo(1)
    assert call_count == 3
    await foo1.foo(1)
    assert call_count == 4
    await foo0.foo(0)
    assert call_count == 5
    await foo1.foo(0)
    assert call_count == 6
