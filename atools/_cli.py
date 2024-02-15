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
import pprint
import re
import types
import typing
import sys

import pydantic


type _Name = str


class _Exception(Exception): ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class _Parser[T]:
    t: type[T]

    type _Arg = bool | float | int | str | list | dict | set | None

    def _parse_arg(self, arg: _Arg, /) -> T:
        match self.t if (origin := typing.get_origin(self.t)) is None else (origin, typing.get_args(self.t)):
            case types.NoneType | None:
                assert arg is None, f'{self} expected `None`, got `{arg}`.'
            case builtins.bool | builtins.int | builtins.float | builtins.str:
                assert isinstance(arg, self.t), f'{self} expected `{self.t}`, got `{arg}`'
            case (builtins.frozenset | builtins.list | builtins.set), (Value,):
                assert isinstance(arg, (list, set))
                arg = origin([_Parser(t=Value)._parse_arg(value) for value in arg])
            case builtins.dict, (Key, Value):
                assert isinstance(arg, dict)
                arg = {_Parser(t=Key)._parse_arg(key): _Parser(t=Value)._parse_arg(value) for key, value in arg.items()}

            case builtins.tuple, ():
                assert arg == tuple()
            case builtins.tuple, (Value,):
                assert isinstance(arg, tuple) and len(arg) == 1
                arg = tuple([_Parser(t=Value)._parse_arg(arg[0])])
            case builtins.tuple, (Value, builtins.Ellipsis):
                assert isinstance(arg, tuple)
                arg = tuple([_Parser(t=Value)._parse_arg(value) for value in arg])
            case builtins.tuple, (Value, *Values):
                assert isinstance(arg, tuple) and len(arg) > 0
                arg = (_Parser(t=Value)._parse_arg(arg[0]), *_Parser(t=tuple[*Values])._parse_arg(arg[1:]))

            case (typing.Union | types.UnionType), Values:
                assert type(arg) in Values
            case typing.Literal, Values:
                assert arg in Values

            case (Value, _) | Value if issubclass(Value, enum.Enum):
                assert isinstance(arg, str) and hasattr(Value, arg)
                arg = getattr(Value, arg)

            case (Value, _) | Value:
                arg = Value(arg)

        return arg

    def parse_arg(self, arg: str, /) -> T:
        """Returns a T parsed from given arg or throws an _Exception upon failure."""

        if self.t != str:
            try:
                arg: _Parser._Arg = ast.literal_eval(arg)
            except (SyntaxError, ValueError,):
                pass

        try:
            value = self._parse_arg(arg)
        except AssertionError as e:
            raise _Exception(f'Could not parse {arg=!r}. {e}.')

        return value


_LogLevelLiteral = typing.Literal['CRITICAL', 'FATAL', 'ERROR', 'WARN', 'WARNING', 'INFO', 'DEBUG', 'NOTSET',]


@dataclasses.dataclass(frozen=True, kw_only=True)
class _Annotation[T]:
    """Generates and collects sane argument defaults intended for argparse.ArgumentParser.add_argument(...).

    Any _Annotation fields that are not `Ellipses` should be passed to <parser instance>.add_argument(...) to add a
    flag.
    """
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

    @staticmethod
    def of_parameter(parameter: inspect.Parameter, /) -> _Annotation[T]:
        """Returns an _Annotation converted from given `parameter`.

        `parameter.annotation` may be of `typing.Annotated[T, <annotations>...]`. If an _Annotation instance is included
        in the annotations, non-Ellipses fields will override anything this method would normally generate. This is
        useful if special argparse behavior for the argument is desired.

        ref. https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_argument
        """

        assert not isinstance(parameter.annotation, str), (
            f'{parameter.annotation=!r} is not evaluated. You may need to manually evaluate this annotation.'
            f' See https://peps.python.org/pep-0563/#resolving-type-hints-at-runtime.'
        )

        annotation = _Annotation()
        t = parameter.annotation

        help_lines = []
        if typing.get_origin(t) is typing.Annotated:
            t, *args = typing.get_args(t)
            help_lines += [*filter(lambda arg: isinstance(arg, str), args)]
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
            match typing.get_origin(t) or type(t):
                case typing.Literal:
                    annotation = dataclasses.replace(annotation, choices=typing.get_args(t))
                case enum.EnumType:
                    annotation = dataclasses.replace(annotation, choices=tuple(t))

        # No automatic actions needed for 'const'.

        if annotation.default is ...:
            if parameter.default != parameter.empty:
                annotation = dataclasses.replace(annotation, default=parameter.default)

        if annotation.help is ...:
            if annotation.default is not ...:
                help_lines.append(f'Default: {annotation.default}')
            if annotation.choices is not ...:
                match typing.get_origin(t) or type(t):
                    case enum.EnumType:
                        choice_names = tuple(map(lambda value: value.name, t))
                    case _:
                        choice_names = tuple(map(str, annotation.choices))
                show_choice_names = tuple(filter(lambda choice_name: not choice_name.startswith('_'), choice_names))
                help_lines.append(
                    f'Choices: {pprint.pformat(show_choice_names, compact=True, width=60)}'
                )
            help_lines.append(f'Type: {typing.Literal if typing.get_origin(t) is typing.Literal else t}')
            annotation = dataclasses.replace(annotation, help='\n'.join(help_lines))

        if annotation.metavar is ...:
            if annotation.choices is not ...:
                annotation = dataclasses.replace(annotation, metavar=f'{{{parameter.name}}}')

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
                annotation = dataclasses.replace(annotation, type=lambda arg: _Parser(t=t).parse_arg(arg))

        return annotation

    @staticmethod
    def log_level_with_logger(logger: logging.Logger, /) -> _Annotation[_LogLevelLiteral]:
        return _Annotation[T](
            choices=typing.get_args(_LogLevelLiteral),
            type=lambda arg: logger.setLevel(value := _Parser(t=_LogLevelLiteral).parse_arg(arg)) or value
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
        parser = argparse.ArgumentParser(
            description=self.decorated.__doc__,
            formatter_class=argparse.RawTextHelpFormatter,
        )

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

        Note that the entrypoint that is run is determined by `self.name` and given `args`.

        ex.
            Given the following registered entrypoints.

                @atools.CLI()  # Registers as f'{__name__}.foo'
                def foo(arg: int) -> ...: ...

                @atools.CLI()  # Registers as f'{__name__}.bar'
                def bar(arg: float) -> ...: ...

                @atools.CLI(f'{__name__}.qux')  # Registers as f'{__name__}.qux'
                async def baz(arg: str) -> ...: ...  # Async entrypoints are also fine.

            Entrypoints may be called like so.
                atools.CLI(__name__).run(['foo', '42'])
                atools.CLI(f'{__name__}.foo').run(['42'])  # Equivalent to previous line.

                atools.CLI(__name__).run(['bar', '3.14'])
                atools.CLI(f'{__name__}.foo').run(['3.14'])  # Equivalent to previous line.

                atools.CLI(__name__).run(['qux', 'Hi!'])
                atools.CLI(f'{__name__}.qux').run(['Hi!'])  # Equivalent to previous line.

        If the entrypoint a couroutinefunction, it will be run via `asyncio.run`.

        Args (Positional or Keyword):
            args (default: sys.argv[1]): Arguments to be parsed and passed to parser's registered entrypoint.

        Returns:
            object: Result of executing entrypoint with given args.
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
                        if remainder_arg.startswith('--'):
                            parser.add_argument(
                                remainder_arg, type=lambda arg: _Parser(t=parameter.annotation).parse_arg(arg)
                            )
                    kwargs.update(vars(parser.parse_args(remainder_args)))
                    remainder_args = []

        assert not parsed_args, f'Unrecognized args: {parsed_args!r}.'
        assert not remainder_args, f'Unrecognized args: {remainder_args!r}.'

        result = self.decorated(*args, **kwargs)
        if inspect.iscoroutinefunction(self.decorated):
            result = asyncio.run(result)

        return result


class _Entrypoint[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, Return]


class _Decorated[** Params, Return](typing.Protocol):
    __call__: typing.Callable[Params, Return]
    cli: _Decoration[Params, Return]


@dataclasses.dataclass(frozen=True)
class _Decorator[** Params, Return]:
    """Decorate a function, adding `.cli` attribute.

    The `.cli.run` function parses command line arguments (e.g. `sys.argv[1:]`) and executes the decorated function with
    the parsed arguments.

    When created, setting `submodules` to True indicates that the decorator should create a hierarchical parser with
    subcommand structure corresponding to submodule structure starting with the decorated function's module. Any module
    with a function name matching given `entrypoint` name have a corresponding CLI subcommand generated with an
    equivalent CLI signature.

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
    Exception: typing.ClassVar[type[_Exception]] = _Exception
    LogLevelLiteral: typing.ClassVar[type[_LogLevelLiteral]] = _LogLevelLiteral
    Name: typing.ClassVar[type[_Name]] = _Name

    def __call__(self, entrypoint: _Entrypoint[Params, Return], /) -> _Decorated[Params, Return]:
        name = self.name if self.name is not ... else '.'.join([entrypoint.__module__, entrypoint.__qualname__])
        name_parts = tuple(filter(lambda name_part: re.match(r'<.+>', name_part) is None, name.split('.')))

        decorated: _Decorated[Params, Return] = entrypoint  # type: ignore

        # Add the entrypoint decoration to the registry.
        decorated.cli = self._registry[name] = _Decoration[Params, Return](
            decorated=decorated, name=','.join(name_parts)
        )

        # Create all the registry links that lead up to the entrypoint decoration.
        for i in range(1, len(name_parts)):
            self._registry.setdefault('.'.join(name_parts[:i]), set()).add(name_parts[i])

        return decorated

    @property
    def _decoration(self) -> _Decoration[Params, Return]:
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

                subcommand_t = typing.Literal[*sorted(value)]  # noqa
                #annotation = _Annotation[subcommand_t](
                #    help='',
                #
                #    metavar=f'{{{','.join(
                #        filter(
                #            lambda choice: not choice.startswith('_'),
                #            map(lambda literal: str(literal), typing.get_args(subcommand_t))
                #        )
                #    )}}}'
                #)

                # Using the local variables in function signature converts the entire annotation to a string without
                #  evaluating it. Rather than let that happen, force evaluation of the annotation.
                #  ref. https://peps.python.org/pep-0563/#resolving-type-hints-at-runtime
                #def decorated(subcommand: typing.Annotated[subcommand_t, annotation]) -> None:
                def decorated(subcommand: subcommand_t) -> None:
                    self.parser.print_usage()
                decorated.__annotations__['subcommand'] = eval(decorated.__annotations__['subcommand'], None, locals())

                decoration = _Decoration[Params, Return](decorated=decorated, name=name)
                decorated.cli = decoration
            case _:  # pragma: no cover
                raise RuntimeError(f'Registry has unhandled item ({name=!r}, {value=!r}).')

        return decoration

    @property
    def parser(self) -> argparse.ArgumentParser:
        return self._decoration.parser

    def run(self, args: typing.Sequence[str] = ...) -> object:
        args = sys.argv[1:] if args is ... else args

        name_parts = [] if self.name is ... else list(filter(
            lambda name_part: re.match(r'<.+>', name_part) is None, self.name.split('.')
        ))
        while args and ('.'.join([*name_parts, args[0]]) in self._registry):
            name_parts.append(args.pop(0))
        name = '.'.join(name_parts)

        return _Decorator(name)._decoration.run(args)


CLI = _Decorator
