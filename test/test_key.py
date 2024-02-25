import atools


def test_key() -> None:
    @atools.Key()
    def foo():
        ...

    assert foo.key == (*__name__.split('.'), test_key.__name__, foo.__name__)
