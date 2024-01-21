#!/usr/bin/env python3
"""CLI entrypoint for all python modules.
"""
from __future__ import annotations
import argparse
import dataclasses
import inspect
import importlib
import logging
import pkgutil
import typing
import sys

log = logging.getLogger(__package__)
logging.basicConfig(level=logging.ERROR)


@dataclasses.dataclass(frozen=True)
class Decorations[** Input, Output]:
    _: dataclasses.KW_ONLY
    cli: CLI[Input, Output]
    parser: argparse.ArgumentParser

    def run(self, args: list[str] = ...) -> object:
        args = sys.argv[1:] if args is ... else args
        parsed_args = vars(self.parser.parse_args(args))

        # Note that this may be the entrypoint of a subparser.
        entrypoint = parsed_args['entrypoint']
        args, kwargs = [], {}
        for parameter in inspect.signature(entrypoint).parameters.values():
            if parameter.kind == parameter.POSITIONAL_ONLY:
                args.append(parsed_args[parameter.name])
            else:
                kwargs[parameter.name] = parsed_args[parameter.name]

        return entrypoint(*args, **kwargs)


class Entrypoint[**Input, Output](typing.Protocol):
    __call__: typing.Callable[Input, Output]


class Decorated[**Input, Output](Entrypoint[Input, Output]):
    decorations: Decorations[Input, Output]


@dataclasses.dataclass(frozen=True)
class CLI[**Input, Output]:
    _: dataclasses.KW_ONLY
    entrypoint_name: str | None = 'entrypoint'
    log_level: str = 'ERROR'
    logger_name: str | None = 'logger'

    @staticmethod
    def set_flag[**Input, Output](parser: argparse.ArgumentParser, entrypoint: Entrypoint[Input, Output], flag) -> None:
        if flag == 'return':
            return

        parameter = inspect.signature(entrypoint).parameters[flag]
        flag = flag.replace('_', '-')
        match (parameter.kind, parameter.default == parameter.empty):
            case (parameter.POSITIONAL_ONLY, False):
                parser.add_argument(
                    flag,
                    default=parameter.default,
                    help=f'default: {parameter.default}',
                    nargs=argparse.OPTIONAL,
                    type=parameter.annotation)
            case (parameter.POSITIONAL_ONLY, True) | (parameter.POSITIONAL_OR_KEYWORD, True):
                parser.add_argument(flag, type=parameter.annotation)
            case (parameter.KEYWORD_ONLY, True):
                parser.add_argument(f'--{flag}', required=True, type=parameter.annotation)
            case (parameter.KEYWORD_ONLY, False) | (parameter.POSITIONAL_OR_KEYWORD, False):
                parser.add_argument(
                    f'--{flag}',
                    default=parameter.default,
                    help=f'default: {parameter.default}',
                    type=parameter.annotation)
            case (parameter.VAR_POSITIONAL, _):
                parser.add_argument(
                    flag,
                    default=parameter.default if parameter.default is not parameter.empty else None,
                    help=f'default: {parameter.default}' if parameter.default is not parameter.empty else None,
                    nargs=argparse.ZERO_OR_MORE,
                    type=parameter.annotation)
            case (parameter.VAR_KEYWORD, _):
                parser.add_argument(
                    f'--{flag}',
                    default=parameter.default if parameter.default is not parameter.empty else None,
                    help=f'default: {parameter.default}' if parameter.default is not parameter.empty else None,
                    nargs=argparse.ZERO_OR_MORE,
                    type=parameter.annotation)
            case _:
                raise RuntimeError(f'During parser setup for {entrypoint=}: {flag=} has unknown {parameter.kind=}.')

    def set_entrypoint(self, module, parser, entrypoint: Entrypoint = ...) -> None:
        if entrypoint is ... and (entrypoint := getattr(module, self.entrypoint_name, None)) is None:
            return

        parser.set_defaults(entrypoint=entrypoint)

        for flag in inspect.get_annotations(entrypoint).keys():
            self.set_flag(parser, entrypoint, flag)

    def set_logger(self, module, parser, logger: logging.Logger = None) -> None:
        if logger is None and (logger := getattr(module, self.logger_name, None)) is None:
            return

        class LogLevelAction(argparse.Action):
            def __call__(self, _parser, namespace, values, option_string=None) -> None:
                level = logging.getLevelNamesMapping()[values]
                logger.setLevel(level)
                setattr(namespace, self.dest, level)

        parser.add_argument(
            '--log-level',
            action=LogLevelAction,
            choices=logging.getLevelNamesMapping().keys(),
            default='ERROR')

    def __call__(self, entrypoint: Entrypoint, /) -> Decorated[Input, Output]:
        module = inspect.getmodule(entrypoint)

        parser = argparse.ArgumentParser(module.__doc__)
        parser.set_defaults(entrypoint=lambda: parser.print_help)

        entrypoint.decorations = Decorations(cli=self, parser=parser)
        # Entrypoint can't reliably be found via inspection of modules as modules may only be partially loaded (this
        #  decorator is likely processed while the module is still loading during import-time).
        stack = [(module, parser, entrypoint)]

        while stack:
            module, parser, entrypoint = stack.pop()
            self.set_entrypoint(module, parser, entrypoint)
            self.set_logger(module, parser)

            if module.__name__ == module.__package__:
                # This is a package. Add its subpackages to the stack to be also be evaluated.
                subparsers = parser.add_subparsers()
                for _, name, _ in pkgutil.iter_modules(path=module.__path__):
                    sub_module = importlib.import_module(f'{module.__package__}.{name}')
                    sub_parser = subparsers.add_parser(name=name, description=sub_module.__doc__)
                    sub_parser.set_defaults(entrypoint=lambda: sub_parser.print_help)
                    stack.append((sub_module, sub_parser, None))

        return entrypoint


cli = CLI()
