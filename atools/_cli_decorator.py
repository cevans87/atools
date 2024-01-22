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
class _Decoration[** Input, Output]:
    _: dataclasses.KW_ONLY
    decorator: _Decorator[Input, Output]
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


class _Entrypoint[** Input, Output](typing.Protocol):
    __call__: typing.Callable[Input, Output]


class _Decorated[** Input, Output](typing.Protocol):
    __call__: typing.Callable[Input, Output]
    cli: _Decoration[Input, Output]


@dataclasses.dataclass(frozen=True)
class _Decorator[** Input, Output]:
    _: dataclasses.KW_ONLY
    entrypoint_name: str | None = None
    log_level: str | None = None
    logger_name: str | None = None

    @staticmethod
    def set_flag[** Input, Output](
        parser: argparse.ArgumentParser,
        entrypoint: _Entrypoint[Input, Output],
        flag: str,
    ) -> None:
        if flag == 'return':
            return

        parameter = inspect.signature(entrypoint).parameters[flag]
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
                parser.add_argument(f'--{flag.replace('_', '-')}', required=True, type=parameter.annotation)
            case (parameter.KEYWORD_ONLY, False) | (parameter.POSITIONAL_OR_KEYWORD, False):
                parser.add_argument(
                    f'--{flag.replace('_', '-')}',
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
                    f'--{flag.replace('_', '-')}',
                    default=parameter.default if parameter.default is not parameter.empty else None,
                    help=f'default: {parameter.default}' if parameter.default is not parameter.empty else None,
                    nargs=argparse.ZERO_OR_MORE,
                    type=parameter.annotation)
            case _:
                raise RuntimeError(f'During parser setup for {entrypoint=}: {flag=} has unknown {parameter.kind=}.')

    def set_entrypoint(self, *, parser, entrypoint: _Entrypoint) -> None:
        parser.set_defaults(entrypoint=entrypoint)

        for flag in inspect.get_annotations(entrypoint).keys():
            self.set_flag(parser, entrypoint, flag)

    def set_logger(self, *, parser, logger: logging.Logger) -> None:
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

    def __call__(self, entrypoint: _Entrypoint, /) -> _Decorated[Input, Output]:

        module = inspect.getmodule(entrypoint)

        parser = argparse.ArgumentParser(module.__doc__)
        parser.set_defaults(entrypoint=lambda: parser.print_help)

        logger = getattr(module, self.logger_name, None)

        entrypoint.cli = _Decoration(decorator=self, parser=parser)
        decorated: _Decorated[Input, Output] = entrypoint  # type: ignore

        # Entrypoint can't reliably be found via inspection of modules as modules may only be partially loaded (this
        #  decorator is likely processed while the module is still loading during import-time).
        stack = [(parser, module, entrypoint, logger)]

        while stack:
            parser, module, entrypoint, logger = stack.pop()

            if module.__name__ == module.__package__:
                # This is a package. Add its subpackages to the stack to be also be evaluated.
                subparsers = parser.add_subparsers()
                for _, name, _ in pkgutil.iter_modules(path=module.__path__):
                    sub_module = importlib.import_module(f'{module.__package__}.{name}')
                    sub_parser = subparsers.add_parser(name=name, description=sub_module.__doc__)
                    sub_parser.set_defaults(entrypoint=lambda: sub_parser.print_help)
                    sub_entrypoint = getattr(sub_module, self.entrypoint_name, None)
                    sub_logger = getattr(sub_module, self.logger_name, None)
                    stack.append((sub_parser, sub_module, sub_entrypoint, sub_logger))

                # TODO(cevans87) the logic here about when to add logger/entrypoint is confusing. Either simplify or
                #  document.
                if logger is not None:
                    self.set_logger(parser=parser, logger=logger)
                if entrypoint is not None:
                    parser = subparsers.add_parser(name='.')

            if logger is not None:
                self.set_logger(parser=parser, logger=logger)

            if entrypoint is not None:
                self.set_entrypoint(parser=parser, entrypoint=entrypoint)

        return decorated


CLI = _Decorator
# TODO see if I can just call the module (as shown in following line) instead of making this default `cli` instance.
cli = CLI(entrypoint_name='main', logger_name='logger', log_level='DEBUG')
__call__ = CLI(entrypoint_name='main', logger_name='logger', log_level='DEBUG').__call__
