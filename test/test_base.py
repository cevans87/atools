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
