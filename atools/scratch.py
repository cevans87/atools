import abc
import dataclasses
import typing


@typing.final
class A(abc.ABC):

    @dataclasses.dataclass
    class B(abc.ABC):
        data: int

        def __new__(cls, data: int, *args, **kwargs):
            if data:
                return object.__new__(A.C)
            else:
                return object.__new__(A.D)


    class C(B):
        ...

    class D(B):
        ...



pass