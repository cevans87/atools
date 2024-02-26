import atools


def test_register() -> None:
    @atools.Register()
    def foo():
        ...

    assert foo.key in foo.register.decoratees
    assert foo.key in foo.register.links
