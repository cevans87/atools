#!/usr/bin/env python3
"""CLI entrypoint for all python modules.
"""
import inspect
from abc import abstractmethod
from argparse import ArgumentParser, Action
from dataclasses import dataclass
from inspect import get_annotations, signature
from importlib import import_module
import logging
import pkgutil
from typing import Optional

log = logging.getLogger(__package__)
logging.basicConfig(level=logging.ERROR)



@dataclass(frozen=True)
class _Cli[Fn]:
    log_level: str = 'ERROR'
    logger_name: Optional[str] = 'logger'

    class Decorated(Fn):
        cli: ArgumentParser

    class RootLogLevelAction(Action):
        def __call__(self, parser, namespace, values, option_string=None) -> None:
            log.setLevel(logging.getLevelNamesMapping()[values])

    def set_log_level_action(self, module, parser) -> None:
        if not (logger_name := self.logger_name) or not hasattr(module, logger_name):
            return

        class LogLevelAction(Action):
            def __call__(self, _parser, namespace, values, option_string=None) -> None:
                getattr(module, logger_name).setLevel(logging.getLevelNamesMapping()[values])

        parser.add_argument(
            '--log-level',
            action=LogLevelAction,
            choices=logging.getLevelNamesMapping().keys(),
            default='ERROR',
        )

    def __call__(self, fn: Fn, /) -> Decorated:
        module = inspect.getmodule(fn)
        parser = ArgumentParser(description=module.__doc__)

        parser.set_defaults(cli_entrypoint=lambda: parser.print_help)

        stack = [(module, parser)]

        while stack:
            module, parser = stack.pop()
            parser.set_defaults(**{module.__package__.replace('.', '_'): True})

            if hasattr(module, 'cli_entrypoint'):
                parser.set_defaults(cli_entrypoint=module.cli_entrypoint)

                for flag, annotation in get_annotations(module.cli_entrypoint).items():
                    if flag == 'return':
                        continue
                    parameter = signature(module.cli_entrypoint).parameters[flag]
                    flag = flag.replace('_', '-')
                    parser.add_argument(
                        f'--{flag}' if parameter.kind == parameter.KEYWORD_ONLY else flag,
                        default=parameter.default,
                        help=f'default: {parameter.default}'
                        if parameter.default is not parameter.empty else None,
                        type=annotation)

            self.set_log_level_action(module, parser)

            if module.__name__ == module.__package__:
                # This is a package. Add its subpackages to the stack to be also be evaluated.
                subparsers = parser.add_subparsers()
                for _, name, _ in pkgutil.iter_modules(path=module.__path__):
                    submodule = import_module(f'{module.__package__}.{name}')
                    subparser = subparsers.add_parser(name=name, description=submodule.__doc__)
                    subparser.set_defaults(cli_entrypoint=lambda: subparser.print_help)
                    stack.append((submodule, subparser))
        else:
            fn.cli = parser

        return fn


def main() -> None:
    args = vars(get_parser(src).parse_args())
    cli_entrypoint = args['cli_entrypoint']
    ks = signature(cli_entrypoint).parameters.keys()
    args['cli_entrypoint'](**{k: args[k] for k in ks})


if __name__ == '__main__':
    main()
