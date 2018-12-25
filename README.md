# atools
Python 3.5+ async-enabled decorators and tools including

- __memoize__ - a function decorator for sync and async functions that memoizes results.
- __async_test (coming soon)__ - a test class/function decorator that enables unittest.TestCase
functions to be async.
- __DevMock (coming soon)__ - a variant of MagicMock that allows first occurrence of a call to pass
through to original code and caches results on filesystem. Subsequent calls to DevMock return
cached results.

## memoize

    Decorates a function call and caches return value for given inputs.

    This decorator is not thread safe but is safe with concurrent awaits.

    If 'size' is provided, memoize will only retain up to 'size' return values.

    If 'expire' is provided, memoize will only retain return values for up to 'expire' duration.
      'expire' duration is given in days, hours, minutes, and seconds like '1d2h3m4s' for 1 day,
      2 hours, 3 minutes, and 4 seconds.

    Examples:

        - Body will run once for unique input 'bar' and result is cached.
            @memoize
            def foo(bar) -> Any: ...

        - Same as above, but async. This also protects against thundering herds.
            @memoize
            async def foo(bar) -> Any: ...

        - Calls to foo(1), foo(bar=1), and foo(1, baz='baz') are equivalent and only cached once.
            @memoize
            def foo(bar, baz='baz'): ...

        - Only 10 items are cached. Acts as an LRU.
            @memoize(size=10)
            def foo(bar, baz) -> Any: ...

       - Items are evicted after 1 minute.
            @memoize(expire='1m')
            def foo(bar) -> Any: ...

## async_test
Coming Soon

## DevMock
Coming Soon
