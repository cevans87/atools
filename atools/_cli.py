#!/usr/bin/env python3

"""Provides `CLI` decorator class and sane-default instantiated `cli` decorator instance.

The decorator may be used to simplify generation of a CLI based entirely on decorated entrypoint function signature.

Single-entrypoint example:

    - file: foo.py
        from atools.cli import CLI


        @CLI()  # This will add `.cli` decoration to `entrypoint`.
        def entrypoint(a: int, /, b: str, c: bool = True, *, d: float, e: tuple = tuple()) -> ...:
            ...


        if __name__ == '__main__':
            # This will parse `sys.argv[1:]` and run entrypoint with parsed arguments.
            entrypoint.cli.run()

    - Command line executions:
        $ ./foo.py 1 "this is b" --d 0.1"
        $ ./foo.py 1 "this is b" --no-c --d 0.1 --e "t0" "t1" "t2"

Multiple-entrypoint example:

    - file: prog/__init__.py
        import atools


        @atools.CLI(submodules=True)  # This will find entrypoints in submodules named `entrypoint`.
        def entrypoint(a: int, /, b: str, c: bool = True, *, d: float, e: tuple = tuple()) -> ...:
            ...

    - file: prog/foo.py
        def entrypoint

    - file: __main__.py
        if __name__ == '__main__':
            # This will parse `sys.argv[1:]` and run entrypoint with parsed arguments.
            entrypoint.cli.run()

"""
from __future__ import annotations
import argparse
import ast
import asyncio
import builtins
import dataclasses
import enum
import inspect
import logging
import re
import types
import typing
import sys

import pydantic


type _Name = str


class _Entrypoint[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, Return]


class _Decorated[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, Return]
    cli: _Decoration[Params, Return]


@dataclasses.dataclass(frozen=True, kw_only=True)
class _Value[T]:
    _primitive_types: typing.ClassVar[frozenset[type]] = frozenset({
        builtins.bool,
        builtins.float,
        builtins.int,
        builtins.str,
    })
    _container_types: typing.ClassVar[frozenset[type]] = frozenset({
        builtins.dict,
        builtins.frozenset,
        builtins.list,
        builtins.set,
        builtins.tuple,
    })
    _types: typing.ClassVar[frozenset[type]] = frozenset(_primitive_types | _container_types)

    @classmethod
    def _of_arg[T](cls, arg: object, t: type[T]) -> T:
        match type(arg), t if (origin := typing.get_origin(t)) is None else (origin, typing.get_args(t)):
            # Primitive types.
            case (
                (builtins.bool, builtins.bool)
                | (builtins.float, builtins.float)
                | (builtins.int, builtins.int)
                | (builtins.str, builtins.str)
                # None and types.NoneType are not the same but are used interchangeably in Python typing.
                | (types.NoneType, (None | types.NoneType))
            ):
                value: T = arg

            # Union type.
            # types.UnionType and typing.Union are not equivalent. If that changes, just use types.UnionType.
            #  ref. https://github.com/python/cpython/issues/105499.
            case Arg, ((types.UnionType | typing.Union), Args) if Arg in Args:
                arg: Arg
                value: T = arg

            # Container types.
            case builtins.dict, (builtins.dict, (Key, Value)):
                arg: dict
                value: T = {cls._of_arg(key, Key): cls._of_arg(value, Value) for key, value in arg.items()}
            case (
                (builtins.set, (builtins.frozenset, (Value,)))
                | (builtins.list, (builtins.list, (Value,)))
                | (builtins.set, (builtins.set, (Value,)))
                | (builtins.tuple, (builtins.tuple, (Value, builtins.Ellipsis)))
            ):
                arg: typing.Iterable[Value]
                value: T = t([cls._of_arg(value, Value) for value in arg])

            # Tuples require evaluation of each arg until none are left.
            case builtins.tuple, (builtins.tuple, (Arg, *Args)):
                arg: tuple
                value: T = tuple([cls._of_arg(arg[0], Arg), *cls._of_arg(arg[1:], tuple[*Args])])
            case builtins.tuple, (builtins.tuple, ()):
                arg: tuple[()]
                value: T = tuple()

            # Custom type.
            case Arg, (Origin, (_)) if Origin not in cls._types:
                arg: Arg
                value: T = Origin(arg)
            case Arg, _ if origin is None and t not in cls._types:
                arg: Arg
                value: T = t(arg)
            case _:
                raise RuntimeError(f'Given {t=!r} could not be enforced on {arg=!r}.')

        return value

    @classmethod
    def of_arg(cls, arg: str, t: type[T]) -> T:
        try:
            arg = ast.literal_eval(arg)
        except (SyntaxError, ValueError,):
            pass

        return cls._of_arg(arg=arg, t=t)


_LogLevelLiteral = typing.Literal['CRITICAL', 'FATAL', 'ERROR', 'WARN', 'WARNING', 'INFO', 'DEBUG', 'NOTSET',]


@dataclasses.dataclass(frozen=True, kw_only=True)
class _Annotation[T]:
    name_or_flags: list[str] = ...
    action: typing.Literal[
        'store',
        'store_const',
        'store_true',
        'store_false',
        'append',
        'append_const',
        'count',
        'help',
        'version',
    ] | typing.Type[argparse.Action] = ...
    choices: typing.Iterable[T] = ...
    const: T = ...
    default: T = ...
    dest: str = ...
    help: str = ...
    metavar: str | None = ...
    nargs: pydantic.NonNegativeInt | typing.Literal[
        '?',
        '*',
        '+'
    ] = ...
    required: bool = ...
    run: tuple[typing.Callable[[T], None]] = ...
    type: typing.Callable[[str], T] = ...

    def __call__(self, **kwargs) -> _Annotation[T]:
        return dataclasses.replace(self, **kwargs)

    @staticmethod
    def of_parameter(parameter: inspect.Parameter, /) -> _Annotation[T]:
        if isinstance(parameter.annotation, str):
            raise RuntimeError(
                f'{parameter.annotation=!r} is a str (e.g. not evaluated).'
                f' See https://peps.python.org/pep-0563/#resolving-type-hints-at-runtime.'
            )

        annotation = _Annotation()

        match parameter.kind:
            case (
                inspect.Parameter.KEYWORD_ONLY
                | inspect.Parameter.POSITIONAL_ONLY
                | inspect.Parameter.POSITIONAL_OR_KEYWORD
                | inspect.Parameter.VAR_POSITIONAL
            ):
                t = parameter.annotation
            case _:  # pragma: no cover
                raise RuntimeError(f'{parameter.name=!r} has unsupported {parameter.kind=!r}.')

        help_parts = []
        if typing.get_origin(t) is typing.Annotated:
            t, *args = typing.get_args(t)
            help_parts += [*filter(lambda arg: isinstance(arg, str), args)]
            for override_add_arguments in filter(lambda arg: isinstance(arg, _Annotation), args):
                annotation = dataclasses.replace(
                    annotation,
                    **dict(filter(lambda item: item[1] is not ..., dataclasses.asdict(override_add_arguments).items()))
                )

        if annotation.name_or_flags is ...:
            match parameter.kind, parameter.default == parameter.empty:
                case (
                    (parameter.POSITIONAL_ONLY, _)
                    | (parameter.VAR_POSITIONAL, True)
                    | (parameter.POSITIONAL_OR_KEYWORD, True)
                ):
                    annotation = dataclasses.replace(annotation, name_or_flags=[parameter.name])
                case (
                    (parameter.KEYWORD_ONLY, _)
                    | (parameter.POSITIONAL_OR_KEYWORD, False)
                ):
                    annotation = dataclasses.replace(
                        annotation, name_or_flags=[f'--{parameter.name.replace('_', '-')}']
                    )

        if annotation.action is ...:
            match parameter.kind:
                case inspect.Parameter.VAR_POSITIONAL:
                    annotation = dataclasses.replace(annotation, action='append')

        if annotation.choices is ...:
            match typing.get_origin(t) or t:
                case typing.Literal:
                    annotation = dataclasses.replace(annotation, choices=typing.get_args(t))
                case enum.Enum:
                    annotation = dataclasses.replace(annotation, choices=(value.name for value in t))

        # No automatic actions needed for 'const'.

        if annotation.default is ...:
            if parameter.default != parameter.empty:
                annotation = dataclasses.replace(annotation, default=parameter.default)

        if annotation.help is ...:
            if annotation.choices is not ...:
                help_parts += [f'{{{','.join(filter(lambda choice: not choice.startswith('_'), annotation.choices))}}}']
            if annotation.default is not ...:
                help_parts += [f'Default:', str(annotation.default)]
            annotation = dataclasses.replace(annotation, help=' '.join(help_parts))

        if annotation.metavar is ...:
            if annotation.choices is not ...:
                annotation = dataclasses.replace(annotation, metavar=parameter.name)

        if annotation.nargs is ...:
            match annotation.action, parameter.kind, parameter.default == parameter.empty:
                case builtins.Ellipsis, (parameter.POSITIONAL_ONLY | parameter.POSITIONAL_OR_KEYWORD), False:
                    annotation = dataclasses.replace(annotation, nargs='?')
                case 'append', (parameter.VAR_POSITIONAL | parameter.VAR_KEYWORD), True:
                    annotation = dataclasses.replace(annotation, nargs='*')

        if annotation.required is ...:
            if (parameter.kind == parameter.KEYWORD_ONLY) and (parameter.default == parameter.empty):
                annotation = dataclasses.replace(annotation, required=True)

        if annotation.type is ...:
            if annotation.action not in {'count', 'store_false', 'store_true'}:
                annotation = dataclasses.replace(annotation, type=lambda arg: _Value.of_arg(arg=arg, t=t))

        return annotation

    @staticmethod
    def log_level_with_logger(logger: logging.Logger, /) -> _Annotation[T: _LogLevelLiteral]:
        return _Annotation[T](
            choices=typing.get_args(_LogLevelLiteral),
            type=lambda arg: logger.setLevel(value := _Value.of_arg(arg=arg, t=str)) or value
        )


@dataclasses.dataclass(frozen=True, kw_only=True)
class _Decoration[** Params, Return]:
    """CLI decoration attached to decorated entrypoint at `<entrypoint>.cli`.

    A _Decoration instance is attached to an entrypoint decorated via _Decorator.__call__. The `run` function can then
    be called with `<entrypoint>.cli.run`.
    """
    decorated: _Decorated[Params, Return]
    name: _Name

    @property
    def parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description=self.decorated.__doc__)

        for parameter in inspect.signature(self.decorated).parameters.values():
            if parameter.kind is inspect.Parameter.VAR_KEYWORD:
                continue
            add_argument_params = dict(
                filter(
                    lambda item: item[1] is not ...,
                    dataclasses.asdict(_Annotation().of_parameter(parameter)).items()
                )
            )
            parser.add_argument(*add_argument_params.pop('name_or_flags'), **add_argument_params)

        return parser

    def run(self, args: typing.Sequence[str] = ...) -> object:
        """Parses args, runs parser's registered entrypoint with parsed args, and return the result.

        Note that the entrypoint that is run is determined by the parser. It may be an entrypoint in a submodule of the
        decorated entrypoint, not the decorated entrypoint.

        If the decorated function is a couroutinefunction, it will be run via `asyncio.run`.

        Args (Positional or Keyword):
            args (default: sys.argv[1]): Arguments to be parsed and passed to parser's registered entrypoint.

        Returns:
            object: Result of executing registered entrypoint with given args.
        """
        args = sys.argv[1:] if args is ... else args

        parsed_args, remainder_args = self.parser.parse_known_args(args)
        parsed_args = vars(parsed_args)

        # Note that this may be the registered entrypoint of a submodule, not the entrypoint that is decorated.
        args, kwargs = [], {}
        for parameter in inspect.signature(self.decorated).parameters.values():
            match parameter.kind:
                case inspect.Parameter.POSITIONAL_ONLY:
                    args.append(parsed_args.pop(parameter.name))
                case inspect.Parameter.POSITIONAL_OR_KEYWORD | inspect.Parameter.KEYWORD_ONLY:
                    kwargs[parameter.name] = parsed_args.pop(parameter.name)
                case inspect.Parameter.VAR_POSITIONAL:
                    args += parsed_args.pop(parameter.name)[0]
                case inspect.Parameter.VAR_KEYWORD:
                    parser = argparse.ArgumentParser()
                    for remainder_arg in remainder_args:
                        if not remainder_arg.startswith('--'):
                            continue
                        parser.add_argument(
                            remainder_arg, type=lambda arg: _Value.of_arg(arg=arg, t=parameter.annotation)
                        )
                    kwargs.update(vars(parser.parse_args(remainder_args)))
                    remainder_args = []

        if parsed_args or remainder_args:
            self.parser.exit()

        result = self.decorated(*args, **kwargs)
        if inspect.iscoroutinefunction(self.decorated):
            result = asyncio.run(result)

        return result


@dataclasses.dataclass(frozen=True)
class _Decorator[** Params, Return]:
    """Decorate a function, adding `<decorated_function>.cli.run` function.

    The `.cli.run` function parses command line arguments (e.g. `sys.argv[1:]`) and executes the decorated function with
    the parsed arguments.

    When created, setting `submodules` to True indicates that the decorator should create a hierarchical parser with
    subcommand structure corresponding to submodule structure starting with the decorated function's module. Any module
    with a function name matching given `entrypoint` name have a corresponding CLI subcommand generated with an
    equivalent CLI signature.

    TODO Mention that types.Dict is equivalent to dict, etc. We get it right, as long as typing.get_origin return an
     instantiable type.

    Parser subcommand documentation is generated from corresponding module docstrings.

    Given a program with the following file structure (column 1), python entrypoints (column 2), the generated CLI
    signature follows (column 3).

              1. Structure          2. entrypoint signature             3. generated CLI signature
        (a)   |- __main__.py                                            prog [-h] {.|foo|baz|quux}
              |- prog
        (b)      |- __init__.py     entrypoint()                        prog . [-h]
                 |- foo.py          entrypoint(pos: int, /)             prog foo [-h] POS
        (a)      |- _bar.py         entrypoint(pos: int = 42, /)        prog _bar [-h] [POS]
                 |- baz
        (c)      |  |- __init__.py  entrypoint(pos_or_kwd: str)         prog baz . [-h] --pos-or-kwd POS_OR_KWD
                 |  |- qux.py       entrypoint(pos_or_kwd: str = 'hi')  prog baz qux [-h] [--pos-or-kwd POS_OR_KWD]
                 |- quux
        (d)         |- __init__.py  entrypoint(*args: list)             Decoration fails with RuntimeError!
        (d)         |- corge.py     entrypoint(**kwargs: dict)          Decoration fails with RuntimeError!

    Note for the diagram above:
        (a) Subcommands that start with underscores are hidden in the CLI signature. They are, however, valid.
        (b) The only `entrypoint` that needs to be decorated is in the toplevel __init__.py.
        (c) Entrypoints in an __init__.py correspond to a `.` CLI subcommand.
        (d) Variadic args and kwargs are unsupported.

    Args (Keyword):
        submodules: If True, subcommands are generated for every submodule in the module hierarchy. CLI bindings are
            generated for each submodule top-level function with name matching decorated entrypoint name.
    """
    name: _Name = ...

    _registry: typing.ClassVar[dict[_Name, _Decoration | set[str]]] = {}

    Annotation: typing.ClassVar[type[_Annotation]] = _Annotation
    LogLevelLiteral: typing.ClassVar[type[_LogLevelLiteral]] = _LogLevelLiteral
    Name: typing.ClassVar[type[_Name]] = _Name

    def __call__(self, entrypoint: _Entrypoint[Params, Return], /) -> _Decorated[Params, Return]:
        name = self.name if self.name is not ... else '.'.join([entrypoint.__module__, entrypoint.__qualname__])
        name_parts = tuple(filter(lambda name_part: re.match(r'<.+>', name_part) is None, name.split('.')))

        # Create all the registry links that lead up to the decorated entrypoint.
        for i in range(len(name_parts)):
            self._registry.setdefault('.'.join(name_parts[:i]), set()).add(name_parts[i])
        name = '.'.join(name_parts)

        # Add the entrypoint decoration to the registry.
        decorated: _Decorated[Params, Return] = entrypoint  # type: ignore
        decorated.cli = self._registry[name] = _Decoration[Params, Return](decorated=entrypoint, name=name)

        return decorated

    @property
    def decoration(self) -> _Decoration[Params, Return]:
        name = '' if self.name is ... else self.name

        match value := self._registry.get(name):
            case _Decoration(decorated=_, name=_):
                decoration = value
            case None:
                def decorated() -> None: ...
                decoration = _Decoration(decorated=decorated, name=name)
                decorated.cli = decoration
            case set(_):
                value: set[str]

                # Using the local `value` in function signature converts the entire annotation to a string without
                #  evaluating it. Rather than let that happen, force evaluation of the annotation.
                #  ref. https://peps.python.org/pep-0563/#resolving-type-hints-at-runtime
                def decorated(
                    subcommand: typing.Annotated[
                        str, _Annotation[str](choices=tuple[str](sorted(value)), metavar='subcommand')
                    ]
                ) -> None:  # pragma: no cover
                    raise RuntimeError('This entrypoint should never execute.')
                decorated.__annotations__['subcommand'] = eval(
                    decorated.__annotations__['subcommand'], locals(), globals()
                )

                decoration = _Decoration[Params, Return](decorated=decorated, name=name)
                decorated.cli = decoration
            case _:  # pragma: no cover
                raise RuntimeError(f'Registry has unhandled item ({name=!r}, {value=!r}).')

        return decoration

    @property
    def parser(self) -> argparse.ArgumentParser:
        return self.decoration.parser

    def run(self, args: typing.Sequence[str] = ...) -> object:
        args = sys.argv[1:] if args is ... else args

        name_parts = [] if self.name is ... else list(filter(
            lambda name_part: re.match(r'<.+>', name_part) is None, self.name.split('.')
        ))
        while args and ('.'.join([*name_parts, args[0]]) in self._registry):
            name_parts.append(args.pop(0))
        name = '.'.join(name_parts)

        return _Decorator(name).decoration.run(args)


CLI = _Decorator
