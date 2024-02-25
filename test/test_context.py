import atools


def test_context() -> None:
    @atools.Context()
    def foo():
        ...

    foo()
