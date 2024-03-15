import typing

import atools._base  # noqa


def test_base() -> None:
    @atools._base.Decorator()
    def foo():
        ...

    foo()


def test_key() -> None:
    @atools._base.Decorator()
    def foo():
        ...

    assert foo.key == (*__name__.split('.'), test_key.__name__, foo.__name__)


def test_register() -> None:
    @atools._base.Decorator()
    def foo():
        ...

    assert foo.key in foo.register.decoratees
    assert foo.key in foo.register.links


def test_method() -> None:

    class Foo:

        @atools._base.Decorator()
        def bar(self, v):
            return locals()

    assert (foo := Foo()).bar(42) == {'self': foo, 'v': 42}


def test_classmethod() -> None:

    class Foo:
        v: typing.ClassVar[int]

        @classmethod
        @atools._base.Decorator()
        def bar(cls, v):
            cls.v = v

    Foo().bar(42)
    assert Foo.v == 42


def test_staticmethod() -> None:

    class Foo:
        v: typing.ClassVar[int]

        @staticmethod
        @atools._base.Decorator()
        def bar(v):
            Foo.v = v

    Foo.bar(42)
    assert Foo.v == 42
