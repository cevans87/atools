#!/usr/bin/env python3
"""CLI entrypoint for all python modules.
"""
from __future__ import annotations
import argparse
import asyncio
import dataclasses
import inspect
import importlib
import pkgutil
import typing
import sys


@dataclasses.dataclass(frozen=True)
class _Decoration[** Params, Return]:
    """CLI decoration with a `.parser` instance and `.run` function.
    """
    _: dataclasses.KW_ONLY
    parser: argparse.ArgumentParser

    def run(self, args: list[str] = ...) -> object:
        f"""Parses args, runs parser's registered entrypoint with parsed args, and return the result.

        Note that the entrypoint that is run is determined by the parser. It may be an entrypoint in a submodule of the
        decorated entrypoint.
        
        If the decorated function is a couroutinefunction, this will run it in the default asyncio event loop.

        Args (Positional or Keyword):
            args (default: sys.argv[1]): Arguments to be parsed and passed to parser's registered entrypoint.

        Returns:
            object: Result of executing parser's registered entrypoint with given args.
        """
        args = sys.argv[1:] if args is ... else args

        parsed_args = vars(self.parser.parse_args(args))

        # Note that this may be the entrypoint of submodule, not the one that is decorated.
        entrypoint = parsed_args['entrypoint']
        args, kwargs = [], {}
        for parameter in inspect.signature(entrypoint).parameters.values():
            if parameter.kind == parameter.POSITIONAL_ONLY:
                args.append(parsed_args[parameter.name])
            else:
                kwargs[parameter.name] = parsed_args[parameter.name]

        result = entrypoint(*args, **kwargs)
        if inspect.iscoroutinefunction(entrypoint):
            result = asyncio.run(result)

        return result


class _Entrypoint[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, Return]


class _Decorated[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, Return]
    cli: _Decoration[Params, Return]


@dataclasses.dataclass(frozen=True)
class _Decorator[** Params, Return]:
    """Decorate a function, adding a `.cli.parser` instance and `.cli.run` function.

    When created, specifying a `submodules_entrypoint_name` indicates that the decorator should create a hierarchical
    parser with subcommand structure corresponding to submodule structure. Any module with a function matching given
    `submodules_entrypoint_name` have a corresponding CLI subcommand generated with an equivalent signature. Note that
    all entrypoints must be fully annotated with types that can be instantiated (e.g. `dict[str, int]` instead of
    `collections.abc.Dict[str, int]`).

    Given a program with the following file structure (column 1), python entrypoints (column 2), the CLI follows
    (column 3).

              1. Structure        2. entrypoint signature             3. generated CLI signature
        (a)   | __main__.py                                           prog [-h] {.|foo|baz|quux}
              + prog
        (b)     | __init__.py     entrypoint()                        prog . [-h]
                | foo.py          entrypoint(pos: int, /)             prog foo [-h] POS
        (a)     | _bar.py         entrypoint(pos: int = 42, /)        prog _bar [-h] [POS]
                + baz
        (c)        | __init__.py   entrypoint(pos_or_kwd: str)         prog baz . [-h] --pos-or-kwd POS_OR_KWD
                  | qux.py        entrypoint(pos_or_kwd: str = 'hi')  prog baz qux [-h] [--pos-or-kwd POS_OR_KWD]
                + quux
        (d)       | __init__.py   entrypoint(*args: list)             RuntimeError!!!
        (d)       | corge.py      entrypoint(**kwargs: dict)          RuntimeError!!!

    Note for the diagram above:
        (a) Subcommands that start with underscores are hidden in the CLI signature. They are, however, valid.
        (b) The only `entrypoint` that needs to be decorated is in the toplevel __init__.py.
        (c) Entrypoints in an __init__.py correspond to a `.` generated subcommand.
        (d) Variadic args and kwargs are unsupported.

    Args (Keyword):
        submodules_entrypoint_name: If given, subcommands are generated for every submodule in the module hierarchy. CLI
            bindings are generated for each entrypoint found in the submodule structure.
    """
    _: dataclasses.KW_ONLY
    submodules_entrypoint_name: str | None = None

    @staticmethod
    def _set_parameter(*, parser: argparse.ArgumentParser, parameter: inspect.Parameter) -> None:
        match (parameter.kind, parameter.default == parameter.empty):
            case (parameter.POSITIONAL_ONLY, True) | (parameter.POSITIONAL_OR_KEYWORD, True):
                parser.add_argument(
                    parameter.name,
                    type=parameter.annotation,
                )
            case (parameter.KEYWORD_ONLY, False) | (parameter.POSITIONAL_OR_KEYWORD, False):
                parser.add_argument(
                    f'--{parameter.name.replace('_', '-')}',
                    default=parameter.default,
                    help=f'default: {parameter.default}',
                    type=parameter.annotation,
                )
            case (parameter.POSITIONAL_ONLY, False):
                parser.add_argument(
                    parameter.name,
                    default=parameter.default,
                    help=f'default: {parameter.default}',
                    nargs=argparse.OPTIONAL,
                    type=parameter.annotation,
                )
            case (parameter.KEYWORD_ONLY, True):
                parser.add_argument(
                    f'--{parameter.name.replace('_', '-')}',
                    required=True,
                    type=parameter.annotation,
                )
            case _:
                raise RuntimeError(f'During parser setup: {parameter.name=} has unsupported {parameter.kind=}.')

    def _set_entrypoint[** SubParams, SubReturn](
        self, *, parser, entrypoint: _Entrypoint[SubParams, SubReturn]
    ) -> None:
        parser.set_defaults(entrypoint=entrypoint)

        for parameter in inspect.signature(entrypoint).parameters.values():
            self._set_parameter(parser=parser, parameter=parameter)

    def __call__(self, entrypoint: _Entrypoint[Params, Return], /) -> _Decorated[Params, Return]:
        module = inspect.getmodule(entrypoint)

        parser = argparse.ArgumentParser(module.__doc__)
        parser.set_defaults(entrypoint=lambda: parser.print_help)

        entrypoint.cli = _Decoration(parser=parser)
        decorated: _Decorated[Params, Return] = entrypoint  # type: ignore

        stack = [(parser, module, entrypoint)]

        while stack:
            parser, module, entrypoint = stack.pop()

            if (self.submodules_entrypoint_name is not None) and (module.__name__ == module.__package__):
                # This is a package. Add its subpackages to the stack to be also be evaluated.
                subparsers = parser.add_subparsers(title='subcommands', metavar='{subcommand}')
                for _, name, _ in pkgutil.iter_modules(path=module.__path__):
                    sub_module = importlib.import_module(f'{module.__package__}.{name}')
                    if name.startswith('_'):
                        sub_parser = subparsers.add_parser(description=sub_module.__doc__, name=name)
                    else:
                        sub_parser = subparsers.add_parser(description=sub_module.__doc__, help='', name=name)
                    sub_parser.set_defaults(entrypoint=lambda: sub_parser.print_help)
                    sub_entrypoint = getattr(sub_module, self.submodules_entrypoint_name, None)
                    stack.append((sub_parser, sub_module, sub_entrypoint))

                if entrypoint is not None:
                    parser = subparsers.add_parser(name='.', help='')

            if entrypoint is not None:
                self._set_entrypoint(parser=parser, entrypoint=entrypoint)

        return decorated


CLI = _Decorator
cli = CLI(submodules_entrypoint_name='entrypoint')
