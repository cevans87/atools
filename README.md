[![Build Status](https://travis-ci.org/cevans87/atools.svg?branch=master&kill_cache=1)](https://travis-ci.org/cevans87/atools)
[![Coverage Status](https://coveralls.io/repos/github/cevans87/atools/badge.svg?branch=master&kill_cache=1)](https://coveralls.io/github/cevans87/atools?branch=master)
# atools
Python 3.6+ decorators including

- `@memoize` - a function decorator for sync and async functions that memoizes results.
- `@rate` - a function decorator for sync and async functions that rate limits calls.

## @memoize
Decorates a function call and caches return value for given inputs.
- If `db_path` is provided, memos will persist on disk and reloaded during initialization.
- If `duration` is provided, memos will only be valid for given `duration`.
- If `keygen` is provided, memo hash keys will be created with given `keygen`.
- If `size` is provided, LRU memo will be evicted if current count exceeds given `size`.

### Examples

- Body will run once for unique input `bar` and result is cached.
    ```python3
    @memoize
    def foo(bar) -> Any: ...

    foo(1)  # Function actually called. Result cached.
    foo(1)  # Function not called. Cached result returned.
    foo(2)  # Function actually called. Result cached.
    ```

- Same as above, but async.
    ```python3
    @memoize
    async def foo(bar) -> Any: ...

    # Concurrent calls from the same event loop are safe. Only one call is generated. The
    # other nine calls in this example wait for the result.
    await asyncio.gather(*[foo(1) for _ in range(10)])
    ```

- Classes may be memoized.
    ```python3
    @memoize
    Class Foo:
        def init(self, _): ...

    Foo(1)  # Instance is actually created.
    Foo(1)  # Instance not created. Cached instance returned.
    Foo(2)  # Instance is actually created.
    ```

- Calls `foo(1)`, `foo(bar=1)`, and `foo(1, baz='baz')` are equivalent and only cached once.
    ```python3
    @memoize
    def foo(bar, baz='baz'): ...
    ```

- Only 2 items are cached. Acts as an LRU.
    ```python3
    @memoize(size=2)
    def foo(bar) -> Any: ...

    foo(1)  # LRU cache order [foo(1)]
    foo(2)  # LRU cache order [foo(1), foo(2)]
    foo(1)  # LRU cache order [foo(2), foo(1)]
    foo(3)  # LRU cache order [foo(1), foo(3)], foo(2) is evicted to keep cache size at 2
    ```

- Items are evicted after 1 minute.
    ```python3
    @memoize(duration=datetime.timedelta(minutes=1))
    def foo(bar) -> Any: ...

    foo(1)  # Function actually called. Result cached.
    foo(1)  # Function not called. Cached result returned.
    sleep(61)
    foo(1)  # Function actually called. Cached result was too old.
    ```

- Memoize can be explicitly reset through the function's `.memoize` attribute
    ```python3
    @memoize
    def foo(bar) -> Any: ...

    foo(1)  # Function actually called. Result cached.
    foo(1)  # Function not called. Cached result returned.
    foo.memoize.reset()
    foo(1)  # Function actually called. Cache was emptied.
    ```

- Current cache length can be accessed through the function's `.memoize` attribute
    ```python3
    @memoize
    def foo(bar) -> Any: ...

    foo(1)
    foo(2)
    len(foo.memoize)  # returns 2
    ```

- Alternate memo hash function can be specified. The inputs must match the function's.
    ```python3
    Class Foo:
        @memoize(keygen=lambda self, a, b, c: (a, b, c))  # Omit 'self' from hash key.
        def bar(self, a, b, c) -> Any: ...

    a, b = Foo(), Foo()

    # Hash key will be (a, b, c)
    a.bar(1, 2, 3)  # LRU cache order [Foo.bar(a, 1, 2, 3)]

    # Hash key will again be (a, b, c)
    # Be aware, in this example the returned result comes from a.bar(...), not b.bar(...).
    b.bar(1, 2, 3)  # Function not called. Cached result returned.
    ```

- If part of the returned key from keygen is awaitable, it will be awaited.
    ```python3
    async def awaitable_key_part() -> Hashable: ...

    @memoize(keygen=lambda bar: (bar, awaitable_key_part()))
    async def foo(bar) -> Any: ...
    ```

- If the memoized function is async and any part of the key is awaitable, it is awaited.
    ```python3
    async def morph_a(a: int) -> int: ...

    @memoize(keygen=lambda a, b, c: (morph_a(a), b, c))
    def foo(a, b, c) -> Any: ...
    ```

- Properties can be memoized.
    ```python3
    Class Foo:
        @property
        @memoize
        def bar(self) -> Any: ...

    a = Foo()
    a.bar  # Function actually called. Result cached.
    a.bar  # Function not called. Cached result returned.

    b = Foo() # Memoize uses 'self' parameter in hash. 'b' does not share returns with 'a'
    b.bar  # Function actually called. Result cached.
    b.bar  # Function not called. Cached result returned.
    ```

- Be careful with eviction on instance methods. Memoize is not instance-specific.
    ```python3
    Class Foo:
        @memoize(size=1)
        def bar(self, baz) -> Any: ...

    a, b = Foo(), Foo()
    a.bar(1)  # LRU cache order [Foo.bar(a, 1)]
    b.bar(1)  # LRU cache order [Foo.bar(b, 1)], Foo.bar(a, 1) is evicted
    a.bar(1)  # Foo.bar(a, 1) is actually called and cached again.
    ```

- Values can persist to disk and be reloaded when memoize is initialized again.
    ```python3
    @memoize(db_path=Path.home() / '.memoize')
    def foo(a) -> Any: ...

    foo(1)  # Function actually called. Result cached.

    # Process is restarted. Upon restart, the state of the memoize decorator is reloaded.

    foo(1)  # Function not called. Cached result returned.
    ```

- If not applied to a function, calling the decorator returns a partial application.
    ```python3
    memoize_db = memoize(db_path=Path.home() / '.memoize')

    @memoize_db(size=1)
    def foo(a) -> Any: ...

    @memoize_db(duration=datetime.timedelta(hours=1))
    def bar(b) -> Any: ...
    ```

- Comparison equality does not affect memoize. Only hash equality matters.
    ```python3
    # Inherits object.__hash__
    class Foo:
        # Don't be fooled. memoize only cares about the hash.
        def __eq__(self, other: Foo) -> bool:
            return True

    @memoize
    def bar(foo: Foo) -> Any: ...

    foo0, foo1 = Foo(), Foo()
    assert foo0 == foo1
    bar(foo0)  # Function called. Result cached.
    bar(foo1)  # Function called again, despite equality, due to different hash.
    ```

### A warning about arguments that inherit `object.__hash__`:

It doesn't make sense to keep a memo if it's impossible to generate the same input again. Inputs
that inherit the default `object.__hash__` are unique based on their id, and thus, their
location in memory. If such inputs are garbage-collected, they are gone forever. For that
reason, when those inputs are garbage collected, `memoize` will drop memos created using those
inputs.

- Memo lifetime is bound to the lifetime of any arguments that inherit `object.__hash__`.
    ```python3
    # Inherits object.__hash__
    class Foo:
        ...

    @memoize
    def bar(foo: Foo) -> Any: ...

    bar(Foo())  # Memo is immediately deleted since Foo() is garbage collected.

    foo = Foo()
    bar(foo)  # Memo isn't deleted until foo is deleted.
    del foo  # Memo is deleted at the same time as foo.
    ```

- Types that have specific, consistent hash functions (int, str, etc.) won't cause problems.
    ```python3
    @memoize
    def foo(a: int, b: str, c: Tuple[int, ...], d: range) -> Any: ...

    foo(1, 'bar', (1, 2, 3), range(42))  # Function called. Result cached.
    foo(1, 'bar', (1, 2, 3), range(42))  # Function not called. Cached result returned.
    ```

- Classmethods rely on classes, which inherit from `object.__hash__`. However, classes are
  almost never garbage collected until a process exits so memoize will work as expected.

    ```python3
    class Foo:
      @classmethod
      @memoize
      def bar(cls) -> Any: ...

    foo = Foo()
    foo.bar()  # Function called. Result cached.
    foo.bar()  # Function not called. Cached result returned.

    del foo  # Memo not cleared since lifetime is bound to class Foo.

    foo = Foo()
    foo.bar()  # Function not called. Cached result returned.
    foo.bar()  # Function not called. Cached result returned.
    ```

- Long-lasting object instances that inherit from `object.__hash__`.

    ```python3
    class Foo:

        @memoize
        def bar(self) -> Any: ...

    foo = Foo()
    foo.bar()  # Function called. Result cached.

    # foo instance is kept around somewhere and used later.
    foo.bar()  # Function not called. Cached result returned.
    ```

## rate
Function decorator that rate limits the number of calls to function.

- `size` must be provided. It specifies the maximum number of calls that may be made
  concurrently and optionally within a given `duration` time window.
- If `duration` is provided it limits the maximum call count to `size` in any given `duration`
  time window.

### Examples
- Only 2 concurrent calls allowed.
    ```python3
    @rate(size=2)
    def foo(): ...
    ```

- Only 2 calls allowed per minute.
    ```python3
    @rate(size=2, duration=60)
    def foo(): ...
    ```

- Same as above, but duration specified with a timedelta.
    ```python3
    @rate(size=2, duration=datetime.timedelta(minutes=1))
    def foo(): ...
    ```

- Same as above, but async.
    ```python3
    @rate(size=2, duration=datetime.timedelta(minutes=1))
    async def foo(): ...
    ```

- More advanced rate limiting is possible by composing multiple rate decorators.
    ```python3
    # Up to 100 calls per minute, but only 10 concurrent.
    @rate(size=100, duration=60)
    @rate(size=10)
    def foo(): ...
    ```
