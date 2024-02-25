import atools


def test_register() -> None:
    @atools.Register()
    def foo():
        ...

    assert foo.key in foo.register.decorateds
    assert foo.key in foo.register.links
