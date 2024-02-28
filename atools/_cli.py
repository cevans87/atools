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
import abc
import annotated_types
import argparse
import ast
import asyncio
import builtins
import dataclasses
import enum
import inspect
import itertools
import logging
import pprint
import types
import typing
import sys

from . import _decoratee
from . import _key
from . import _register


class _Exception(Exception):
    ...


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


@dataclasses.dataclass(frozen=True, kw_only=True)
class _AddArgument[T]:
    """Generates and collects sane argument defaults intended for argparse.ArgumentParser.add_argument(...).

    Any _Annotation fields that are not `Ellipses` should be passed to <parser instance>.add_argument(...) to add a
    flag.
    """
    name_or_flags: list[str] = ...
    action: typing.Type[argparse.Action] | typing.Literal[
        'store',
        'store_const',
        'store_true',
        'store_false',
        'append',
        'append_const',
        'count',
        'help',
        'version',
    ] = ...
    choices: typing.Iterable[T] = ...
    const: T = ...
    default: T = ...
    dest: str = ...
    help: str = ...
    metavar: str | None = ...
    nargs: typing.Annotated[int, annotated_types.Ge(0)] | typing.Literal[
        '?',
        '*',
        '+'
    ] = ...
    required: bool = ...
    type: typing.Callable[[str], T] = ...

    @staticmethod
    def of_parameter(parameter: inspect.Parameter, /) -> _AddArgument[T]:
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

        add_argument = _AddArgument()
        t = parameter.annotation

        help_lines = []
        if typing.get_origin(t) is typing.Annotated:
            t, *args = typing.get_args(t)
            help_lines += [*filter(lambda arg: isinstance(arg, str), args)]
            for override_add_arguments in filter(lambda arg: isinstance(arg, _AddArgument), args):
                add_argument = dataclasses.replace(
                    add_argument,
                    **dict(filter(
                        lambda item: item[1] is not ...,
                        dataclasses.asdict(override_add_arguments).items(),
                    )),
                )

        if add_argument.name_or_flags is ...:
            match parameter.kind, parameter.default == parameter.empty:
                case (
                (parameter.POSITIONAL_ONLY, _)
                | ((parameter.VAR_POSITIONAL | parameter.POSITIONAL_OR_KEYWORD), True)
                ):
                    add_argument = dataclasses.replace(add_argument, name_or_flags=[parameter.name])
                case (parameter.KEYWORD_ONLY, _) | (parameter.POSITIONAL_OR_KEYWORD, False):
                    add_argument = dataclasses.replace(
                        add_argument, name_or_flags=[f'--{parameter.name.replace('_', '-')}']
                    )

        if add_argument.action is ...:
            match parameter.kind:
                case inspect.Parameter.VAR_POSITIONAL:
                    add_argument = dataclasses.replace(add_argument, action='append')

        if add_argument.choices is ...:
            match typing.get_origin(t) or type(t):
                case typing.Literal:
                    add_argument = dataclasses.replace(add_argument, choices=typing.get_args(t))
                case enum.EnumType:
                    add_argument = dataclasses.replace(add_argument, choices=tuple(t))

        # No automatic actions needed for 'const'.

        if add_argument.default is ...:
            if parameter.default != parameter.empty:
                add_argument = dataclasses.replace(add_argument, default=parameter.default)

        if add_argument.help is ...:
            if add_argument.default is not ...:
                help_lines.append(f'default: {add_argument.default!r}')
            if add_argument.choices is not ...:
                match typing.get_origin(t) or type(t):
                    case enum.EnumType:
                        choice_names = tuple(map(lambda value: value.name, t))
                    case _:
                        choice_names = tuple(map(str, add_argument.choices))
                show_choice_names = tuple(filter(lambda choice_name: not choice_name.startswith('_'), choice_names))
                help_lines.append(
                    f'choices: {pprint.pformat(show_choice_names, compact=True, width=60)}'
                )
            help_lines.append(f'type: {typing.Literal if typing.get_origin(t) is typing.Literal else t!r}')
            add_argument = dataclasses.replace(add_argument, help='\n'.join(help_lines))

        if add_argument.metavar is ...:
            if add_argument.choices is not ...:
                add_argument = dataclasses.replace(add_argument, metavar=f'{{{parameter.name}}}')

        if add_argument.nargs is ...:
            match add_argument.action, parameter.kind, parameter.default == parameter.empty:
                case builtins.Ellipsis, (parameter.POSITIONAL_ONLY | parameter.POSITIONAL_OR_KEYWORD), False:
                    add_argument = dataclasses.replace(add_argument, nargs='?')
                case 'append', (parameter.VAR_POSITIONAL | parameter.VAR_KEYWORD), True:
                    add_argument = dataclasses.replace(add_argument, nargs='*')

        if add_argument.required is ...:
            if (parameter.kind == parameter.KEYWORD_ONLY) and (parameter.default == parameter.empty):
                add_argument = dataclasses.replace(add_argument, required=True)

        if add_argument.type is ...:
            if add_argument.action not in {'count', 'store_false', 'store_true'}:
                add_argument = dataclasses.replace(add_argument, type=lambda arg: _Parser(t=t).parse_arg(arg))

        return add_argument


# Override __init__ so that we can make `_side_effect` positional-only while instantiating.
@dataclasses.dataclass(frozen=True, init=False)
class _SideEffect[T]:
    _side_effect: typing.Callable[[T], T]

    def __init__(self, _side_effect: typing.Callable[[T], T], /) -> None:
        object.__setattr__(self, '_side_effect', _side_effect)


_LogLevelInt = typing.Annotated[int, annotated_types.Interval(ge=10, le=60)]
_LogLevelStr = typing.Literal['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET']
_LogLevel = _LogLevelInt | _LogLevelStr


@dataclasses.dataclass(frozen=True, kw_only=True)
class _Annotated:

    LogLevelStr: typing.ClassVar[type[_LogLevelStr]] = _LogLevelStr
    LogLevelInt: typing.ClassVar[type[_LogLevelInt]] = _LogLevelInt
    LogLevel: typing.ClassVar[type[_LogLevel]] = _LogLevel

    @staticmethod
    def quiet(logger_or_name: logging.Logger | str, /) -> type[_LogLevelInt]:
        logger = logger_or_name if isinstance(logger_or_name, logging.Logger) else logging.getLogger(logger_or_name)

        class QuietAction(argparse.Action):
            def __call__(
                self, parser: argparse.ArgumentParser, namespace: argparse.Namespace, values: list[object],
                option_string=None
            ) -> None:
                logger.setLevel(level := min(getattr(namespace, self.dest) + 10, logging.CRITICAL + 10))
                setattr(namespace, self.dest, level)

        return typing.Annotated[
            _LogLevelInt,
            _AddArgument[_LogLevelInt](name_or_flags=['-q', '--quiet'], action=QuietAction, nargs=0),
            _SideEffect[_LogLevelInt](lambda verbose: logger.setLevel(verbose))
        ]

    @staticmethod
    def verbose(logger_or_name: logging.Logger | str, /) -> type[_LogLevelInt]:
        logger = logger_or_name if isinstance(logger_or_name, logging.Logger) else logging.getLogger(logger_or_name)

        class VerboseAction(argparse.Action):
            def __call__(
                self, parser: argparse.ArgumentParser, namespace: argparse.Namespace, values: list[object],
                option_string=None
            ) -> None:
                logger.setLevel(level := max(getattr(namespace, self.dest) - 10, logging.DEBUG))
                setattr(namespace, self.dest, level)

        return typing.Annotated[
            _LogLevelInt,
            _AddArgument[_LogLevelInt](name_or_flags=['-v', '--verbose'], action=VerboseAction, nargs=0),
            _SideEffect[_LogLevelInt](lambda verbose: logger.setLevel(verbose))
        ]

    @staticmethod
    def log_level(logger_or_name: logging.Logger | str, /) -> type[_LogLevelStr]:
        logger = logger_or_name if isinstance(logger_or_name, logging.Logger) else logging.getLogger(logger_or_name)

        return typing.Annotated[
            _LogLevelStr,
            _AddArgument[_LogLevelStr](name_or_flags=['-l', '--log-level']),
            _SideEffect[_LogLevelStr](lambda log_level: logger.setLevel(log_level))
        ]


@dataclasses.dataclass(frozen=True, kw_only=True)
class _Persist[** Params, Return]:
    ...
    # TODO: Make a sticky flag that memoizes a flag.


Decoratee = _decoratee.Decorated


@typing.final
class Decoration:

    @dataclasses.dataclass(kw_only=True)
    class Base[** Params, Return]:
        ...

    @dataclasses.dataclass(kw_only=True)
    class Async[** Params, Return](Base[Params, Return]):
        decoratee: Decoratee.Async[Params, Return]

    @dataclasses.dataclass(kw_only=True)
    class Multi[** Params, Return](Base[Params, Return]):
        decoratee: Decoratee.Multi[Params, Return]

    @dataclasses.dataclass(kw_only=True)
    class Top[** Params, Return](Async[Params, Base], Multi[Params, Return]):
        ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class Decoration:
    """CLI decoration attached to decorated entrypoint at `<entrypoint>.cli`.

    A _Decoration instance is attached to an entrypoint decorated via _Decorator.__call__. The `run` function can then
    be called with `<entrypoint>.cli.run`.
    """

    @dataclasses.dataclass(kw_only=True)
    class Base[** Params, Return]:
        decoratee: Decorated[Params, Return].Base
        parser: argparse.ArgumentParser = dataclasses.field(default_factory=argparse.ArgumentParser)

        @property
        def parser(self) -> argparse.ArgumentParser:
            signature = inspect.signature(self.decoratee)
            parser = argparse.ArgumentParser(
                description='\n'.join(filter(None, [
                    self.decoratee.__doc__,
                    f'return type: {pprint.pformat(signature.return_annotation, compact=True, width=75)}'
                ])),
                formatter_class=argparse.RawTextHelpFormatter
            )

            for parameter in signature.parameters.values():
                if parameter.kind is inspect.Parameter.VAR_KEYWORD:
                    # Var keywords will are parsed on a second pass.
                    continue
                add_argument_params = dict(
                    filter(
                        lambda item: not isinstance(item[1], typing.Hashable) or item[1] is not ...,
                        dataclasses.asdict(_AddArgument().of_parameter(parameter)).items()
                    )
                )
                parser.add_argument(*add_argument_params.pop('name_or_flags'), **add_argument_params)

            return parser

        def __call__(self, args: typing.Sequence[str] = ...) -> typing.Awaitable[object] | object:
            """Parses args, runs parser's registered entrypoint with parsed args, and return the result.

            Note that the entrypoint that is run is determined by `self.name` and given `args`.

            Ex.
                Given the following registered entrypoints.

                    @atools.CLI()  # Automatically registered as f'{__name__}.foo'
                    def foo(arg: int) -> ...: ...

                    @atools.CLI()  # Automatically registered as f'{__name__}.bar'
                    def bar(arg: float) -> ...: ...

                    @atools.CLI(f'{__name__}.qux')  # Manually registered as f'{__name__}.qux'
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
                args: Arguments to be parsed and passed to parser's registered entrypoint.
                    Default: sys.argv[1:]

            Returns:
                object: Result of executing registered entrypoint with given args.
            """
            args = sys.argv[1:] if args is ... else args

            parsed_ns, remainder_args = self.parser.parse_known_args(args)
            parsed_args = vars(parsed_ns)

            # Note that this may be the registered entrypoint of a submodule, not the entrypoint that is decorated.
            args, kwargs = [], {}
            for parameter in inspect.signature(self.decoratee).parameters.values():
                side_effects = []
                if typing.get_origin(parameter.annotation) is typing.Annotated:
                    for annotation in typing.get_args(parameter.annotation):
                        match annotation:
                            case _SideEffect(side_effect):
                                side_effects.append(side_effect)

                side_effect = [
                    *itertools.accumulate(side_effects, func=lambda x, y: lambda z: x(y(z)), initial=lambda x: x)
                ][-1]

                values = []
                match parameter.kind:
                    case inspect.Parameter.POSITIONAL_ONLY:
                        values = [parsed_args.pop(parameter.name)]
                        args.append(side_effect(values[0]))
                    case inspect.Parameter.POSITIONAL_OR_KEYWORD | inspect.Parameter.KEYWORD_ONLY:
                        values = [parsed_args.pop(parameter.name)]
                        kwargs[parameter.name] = values[0]
                    case inspect.Parameter.VAR_POSITIONAL:
                        values = [parsed_args.pop(parameter.name)][0][0]
                        args += values
                    case inspect.Parameter.VAR_KEYWORD:
                        parser = argparse.ArgumentParser()
                        for remainder_arg in remainder_args:
                            if remainder_arg.startswith('--'):
                                parser.add_argument(
                                    remainder_arg, type=lambda arg: _Parser(t=parameter.annotation).parse_arg(arg)
                                )
                        remainder_ns = parser.parse_args(remainder_args)
                        remainder_args = []
                        remainder_kwargs = dict(vars(remainder_ns).items())

                        values = remainder_kwargs.values()
                        kwargs.update(remainder_kwargs)

                [side_effect(value) for side_effect in side_effects for value in values]

            assert not parsed_args, f'Unrecognized args: {parsed_args!r}.'
            assert not remainder_args, f'Unrecognized args: {remainder_args!r}.'

            return self.decoratee(*args, **kwargs)

    @dataclasses.dataclass
    class Async(Base):
        async def __call__(self, args: typing.Sequence[str] = ...) -> object:
            return await super().__call__(args=args)

    @dataclasses.dataclass
    class Multi(Base):
        ...

    @dataclasses.dataclass
    class Top(Async, Multi, abc.ABC):

        @typing.overload
        async def __call__(self, args: typing.Sequence[str] = ...) -> object: ...

        @typing.overload
        def __call__(self, args: typing.Sequence[str] = ...) -> object: ...

        def __call__(self, args: typing.Sequence[str] = ...) -> typing.Awaitable[object] | object: ...


CLI = Decoration


decoratee = _decoratee.Decorated


@typing.final
class Decorated(abc.ABC):

    @dataclasses.dataclass(kw_only=True)
    class Base[** Params, Return]:
        cli: CLI.Top[Params, Return]

        def __call__(self, *args: Params.args, **kwargs: Params.kwargs) -> typing.Awaitable[Return] | Return:
            args = sys.argv[1:] if args is ... else args

            parsed_ns, remainder_args = self.cli.parser.parse_known_args(args)
            parsed_args = vars(parsed_ns)

            # Note that this may be the registered entrypoint of a submodule, not the entrypoint that is decorated.
            args, kwargs = [], {}
            for parameter in inspect.signature(self.cli.decoratee).parameters.values():
                side_effects = []
                if typing.get_origin(parameter.annotation) is typing.Annotated:
                    for annotation in typing.get_args(parameter.annotation):
                        match annotation:
                            case _SideEffect(side_effect):
                                side_effects.append(side_effect)

                side_effect = [
                    *itertools.accumulate(side_effects, func=lambda x, y: lambda z: x(y(z)), initial=lambda x: x)
                ][-1]

                values = []
                match parameter.kind:
                    case inspect.Parameter.POSITIONAL_ONLY:
                        values = [parsed_args.pop(parameter.name)]
                        args.append(side_effect(values[0]))
                    case inspect.Parameter.POSITIONAL_OR_KEYWORD | inspect.Parameter.KEYWORD_ONLY:
                        values = [parsed_args.pop(parameter.name)]
                        kwargs[parameter.name] = values[0]
                    case inspect.Parameter.VAR_POSITIONAL:
                        values = [parsed_args.pop(parameter.name)][0][0]
                        args += values
                    case inspect.Parameter.VAR_KEYWORD:
                        parser = argparse.ArgumentParser()
                        for remainder_arg in remainder_args:
                            if remainder_arg.startswith('--'):
                                parser.add_argument(
                                    remainder_arg, type=lambda arg: _Parser(t=parameter.annotation).parse_arg(arg)
                                )
                        remainder_ns = parser.parse_args(remainder_args)
                        remainder_args = []
                        remainder_kwargs = dict(vars(remainder_ns).items())

                        values = remainder_kwargs.values()
                        kwargs.update(remainder_kwargs)

                [side_effect(value) for side_effect in side_effects for value in values]

            assert not parsed_args, f'Unrecognized args: {parsed_args!r}.'
            assert not remainder_args, f'Unrecognized args: {remainder_args!r}.'

            return self.cli.decoratee(*args, **kwargs)

    class Async[** Params, Return](Base[Params, Return]):
        __call__: typing.Callable[Params, typing.Awaitable[Return]]

    class Multi[** Params, Return](Base[Params, Return]):
        __call__: typing.Callable[Params, Return]

    type Top[** Params, Return] = Decorated.Async[Params, Return] | Decorated.Multi[Params, Return]
    ...


@dataclasses.dataclass(frozen=True)
class Decorator:
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

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class Base[** Params, Return](_key.Decorator.Base):

        @property
        def parser(self) -> argparse.ArgumentParser:
            return self.cli.parser

        @property
        def cli(self) -> Decoration:
            register = _register.Decorator.Top[Params, Return](self._prefix, self._suffix).register
            key = _key.Decorator.Top[Params, Return](self._prefix, self._suffix).key

            if (
                ((decoratee := register.decoratees.get(key)) is None)
                or not (isinstance(decorated, Decorated))
            ):
                @Decorator.Top[Params, Return]('.'.join(key))
                def decorated(subcommand: typing.Literal[*sorted(register.links.get(key, set()))]) -> None:  # noqa
                    self.parser.print_usage()

                # Using the local variables in function signature converts the entire annotation to a string without
                #  evaluating it. Rather than let that happen, force evaluation of the annotation.
                #  ref. https://peps.python.org/pep-0563/#resolving-type-hints-at-runtime
                decorated.__annotations__['subcommand'] = eval(decorated.__annotations__['subcommand'], None, locals())
                #decorated: Decorated = decoratee  # noqa

            return decorated.cli

        def run(self, args: typing.Sequence[str] = ...) -> object:
            args = sys.argv[1:] if args is ... else args
            register = _register.Decorator[Params, Return].Top(self._prefix, self._suffix).get_register()
            key = _key.Decorator.Base(self._prefix, self._suffix).key

            while args and (tuple([*key, args[0]]) in register.links):
                key = tuple([*key, args.pop(0)])

            return Decorator.Top('.'.join(key)).cli.run(args)

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class Async[** Params, Return](Base[Params, Return]):
        ...

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class Multi[** Params, Return](Base[Params, Return]):
        ...

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class Top[** Params, Return]():

        @typing.overload
        def __call__(
            self, decoratee: Decoratee.Async[Params, Return], /
        ) -> Decorated.Async[[typing.Sequence[str]], Return]: ...

        @typing.overload
        def __call__(
            self, decoratee: Decoratee.Multi[Params, Return], /
        ) -> Decorated.Multi[typing.Sequence[str], Return]: ...

        def __call__(
            self, decoratee: Decoratee.Top[Params, Return], /
        ) -> Decorated.Top[typing.Sequence[str], Return]:
            decoratee = _register.Decorator.Top[Params, Return](self._prefix, self._suffix)(decoratee)

            if inspect.iscoroutinefunction(decoratee):
                decorated = Decorated.Async[Params, Return](cli=CLI.Multi[Params, Return](decoratee))
            else:
                decorated = Decorated.Multi[Params, Return](cli=CLI.Multi[Params, Return](decoratee))

            return decorated

