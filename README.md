[![Build Status](https://travis-ci.org/cevans87/atools.svg?branch=master&kill_cache=1)](https://travis-ci.org/cevans87/atools)
[![Coverage Status](https://coveralls.io/repos/github/cevans87/atools/badge.svg?branch=master&kill_cache=1)](https://coveralls.io/github/cevans87/atools?branch=master)
# atools
Python 3.6+ async-enabled decorators and tools including

- __memoize__ - a function decorator for sync and async functions that memoizes results.
- __async_test_case__ - a test class/function decorator that enables test functions to be async.
- __rate__ - a function decorator for sync and async functions that rate limits calls.

## memoize
    Decorates a function call and caches return value for given inputs.

    If 'size' is provided, memoize will only retain up to 'size' return values.

    If 'expire' is provided, memoize will only retain return values for up to 'expire' duration.

    Examples:

        - Body will run once for unique input 'bar' and result is cached.
            @memoize
            def foo(bar) -> Any: ...

            foo(1)  # Function actually called. Result cached.
            foo(1)  # Function not called. Previously-cached result returned.
            foo(2)  # Function actually called. Result cached.

        - Same as above, but async.
            @memoize
            async def foo(bar) -> Any: ...

            # Concurrent calls from the same thread are safe. Only one call is generated. The
            other nine calls in this example wait for the result.
            await asyncio.gather(*[foo(1) for _ in range(10)])

        - Classes may be memoized.
            @memoize
            Class Foo:
                def init(self, _): ...

            Foo(1)  # Instance is actually created.
            Foo(1)  # Instance not created. Previously-cached instance returned.
            Foo(2)  # Instance is actually created.

        - Calls to foo(1), foo(bar=1), and foo(1, baz='baz') are equivalent and only cached once
            @memoize
            def foo(bar, baz='baz'): ...

        - Only 10 items are cached. Acts as an LRU.
            @memoize(size=2)
            def foo(bar) -> Any: ...

            foo(1)  # LRU cache order [foo(1)]
            foo(2)  # LRU cache order [foo(1), foo(2)]
            foo(1)  # LRU cache order [foo(2), foo(1)]
            foo(3)  # LRU cache order [foo(1), foo(3)], foo(2) is evicted to keep cache size at 2

       - Items are evicted after 1 minute.
            @memoize(duration=datetime.timedelta(minutes=1))
            def foo(bar) -> Any: ...

            foo(1)  # Function actually called. Result cached.
            foo(1)  # Function not called. Previously-cached result returned.
            sleep(61)
            foo(1)  # Function actually called. Previously-cached result was too old.

        - Memoize can be explicitly reset through the function's 'memoize' attribute
            @memoize
            def foo(bar) -> Any: ...

            foo(1)  # Function actually called. Result cached.
            foo(1)  # Function not called. Previously-cached result returned.
            foo.memoize.reset()
            foo(1)  # Function actually called. Cache was emptied.

        - Current cache size can be accessed through the function's 'memoize' attribute
            @memoize
            def foo(bar) -> Any: ...

            foo(1)
            foo(2)
            len(foo.memoize)  # returns 2

        - Properties can be memoized
            Class Foo:
                @property
                @memoize
                def bar(self, baz): -> Any: ...

            a = Foo()
            a.bar  # Function actually called. Result cached.
            a.bar  # Function not called. Previously-cached result returned.

            b = Foo() # Memoize uses 'self' parameter in hash. 'b' does not share returns with 'a'
            b.bar  # Function actually called. Result cached.
            b.bar  # Function not called. Previously-cached result returned.

        - Be careful with eviction on instance methods.
            Class Foo:
                @memoize(size=1)
                def foo(self): -> Any: ...

            a, b = Foo(), Foo()
            a.bar(1)  # LRU cache order [Foo.bar(a)]
            b.bar(1)  # LRU cache order [Foo.bar(b)], Foo.bar(a) is evicted
            a.bar(1)  # Foo.bar(a, 1) is actually called cached and again.

## async_test_case
    Decorates a test function or test class to enable running async test functions.

    Examples:
        - After decorating a test function, simply calling it will run it.
            async def test_foo(): -> None: ...

            test_foo()  # Returns a coroutine, but it wasn't awaited, so the test didn't run.

            @async_test_case
            async def test_foo(): -> None: ...

            test_foo()  # The decorator awaits the decorated function.

        - Test class may be decorated. All async functions with names starting with 'test' are
          decorated.
            @async_test_case
            Class TestFoo(unittest.TestCase):
                # All of these functions are decorated. Nothing else is needed for them to run.
                async def test_foo(self) -> None: ...
                async def test_bar(self) -> None: ...
                async def test_baz(self) -> None: ...

## rate                
    Function decorator that rate limits the number of calls to function.

    'size' must be provided. It specifies the maximum number of calls that may be made concurrently
      and optionally within a given 'duration' time window.

    If 'duration' is provided, the maximum number of calls is limited to 'size' calls in any given
      'duration' time window.

    if 'thread_safe' is True, the decorator is guaranteed to be thread safe.

    Examples:
        - Only 2 concurrent calls allowed.
            @rate(size=2)
            async def foo(): ...

        - Only 2 calls allowed per minute.
            @rate(size=2, duration=60)
            async def foo(): ...

        - Same as above, but duration specified with a timedelta.
            @rate_window(size=2, duration=datetime.timedelta(minutes=1))
            async def foo(): ...

        - Same as above, but thread safe.
            @rate_window(size=2, duration=datetime.timedelta(minutes=1), thread_safe=True)
            def foo(): ...
