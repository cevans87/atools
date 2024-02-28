import atools


def test_base() -> None:
    @atools.Base()
    def foo():
        ...

    foo()
