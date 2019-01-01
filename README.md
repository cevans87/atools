[![Build Status](https://travis-ci.org/cevans87/atools.svg?branch=master&kill_cache=1)](https://travis-ci.org/cevans87/atools)
[![Coverage Status](https://coveralls.io/repos/github/cevans87/atools/badge.svg?branch=master&kill_cache=1)](https://coveralls.io/github/cevans87/atools?branch=master)
# atools
Python 3.7+ async-enabled decorators and tools including

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
      'expire' duration is given in seconds or a string such as '10s', '1m', or '1d1h1m1s' where
      days, hours, minutes, and seconds are represented by 'd', 'h', 'm', and 's' respectively.

    If 'pass_unhashable' is True, memoize will not remember calls that are made with parameters
      that cannot be hashed instead of raising an exception.

    if 'thread_safe' is True, the decorator is guaranteed to be thread safe.

    Examples:

        - Body will run once for unique input 'bar' and result is cached.
            @memoize
            def foo(bar) -> Any: ...

        - Same as above, but async. Concurrent calls with the same 'bar' are safe and will only
          generate one call
            @memoize
            async def foo(bar) -> Any: ...

        - Calls to foo(1), foo(bar=1), and foo(1, baz='baz') are equivalent and only cached once
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
