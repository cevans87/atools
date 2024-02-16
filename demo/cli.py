import dataclasses
import enum
import logging
import typing

import atools

logger = logging.getLogger(__name__)


@atools.CLI()
def simple_arg(arg: str) -> None:
    """Demo for CLI with an arg.

    Ex:
        python3 -m demo cli positional_only_without_defaults 42 Hi!
    """
    print(locals())


@atools.CLI()
def simple_arg_with_help_text(
    arg: typing.Annotated[str, 'typing.Annotated[<T>, help_text] allows you to give CLI help text for parameter.'],
) -> None:
    """Demo for CLI entrypoint with positional-only args without defaults.

    Ex:
        python3 -m demo cli positional_only_without_defaults 42 Hi!
    """
    print(locals())


@atools.CLI()
def positional_only_without_defaults(
    foo: typing.Annotated[int, 'A positional-only foo without default. Is positional-only in CLI.'],
    bar: typing.Annotated[str, 'A positional-only bar without default. Is positional-only in CLI.'],
    /,
) -> None:
    """Demo for CLI entrypoint with positional-only args without defaults.

    Ex:
        python3 -m demo cli positional_only_without_defaults 42 Hi!
    """
    print(locals())


@atools.CLI()
def positional_or_keyword_without_defaults(
    foo: typing.Annotated[float, 'A positional-or-keyword foo without default. Is positional-only in CLI.'],
    bar: typing.Annotated[bool, 'A positional-or-keyword bar without default. Is positional-only in CLI.'],
) -> None:
    """Demo for CLI entrypoint with positional-or-keyword args without defaults.

    Ex:
        python3 -m demo cli keyword_only_without_defaults --foo 3.14 --bar True
    """
    print(locals())


@atools.CLI()
def keyword_only_without_defaults(
    *,
    foo: typing.Annotated[float, 'A keyword-only foo without default. Is keyword-only in CLI.'],
    bar: typing.Annotated[bool, 'A keyword-only bar without default. Is keyword-only in CLI.'],
) -> None:
    """Demo for CLI entrypoint with keyword-only args without defaults.

    Ex:
        python3 -m demo cli keyword_only_without_defaults --foo 3.14 --bar True
    """
    print(locals())


@atools.CLI()
def positional_only_with_defaults(
    foo: typing.Annotated[int, 'A positional-only foo with default. Is positional-only in CLI.'] = 0,
    bar: typing.Annotated[str, 'A positional-only bar with default. Is positional-only in CLI.'] = 'Bye!',
    /,
) -> None:
    """Demo for CLI entrypoint with positional-only args with defaults.

    Ex:
        python3 -m demo cli keyword_only_without_defaults
        python3 -m demo cli keyword_only_without_defaults 42
        python3 -m demo cli keyword_only_without_defaults 42 Hi!
    """
    print(locals())


@atools.CLI()
def positional_or_keyword_with_defaults(
    foo: typing.Annotated[float, 'A positional-or-keyword foo with default. Is keyword-only in CLI.'] = 0.0,
    bar: typing.Annotated[bool, 'A positional-or-keyword bar with default. Is keyword-only in CLI.'] = False,
) -> None:
    """Demo for CLI entrypoint with positional-or-keyword args with defaults.

    Ex:
        python3 -m demo cli keyword_only_without_defaults
        python3 -m demo cli keyword_only_without_defaults --foo 3.14
        python3 -m demo cli keyword_only_without_defaults --bar True
        python3 -m demo cli keyword_only_without_defaults --foo 3.14 --bar True
        python3 -m demo cli keyword_only_without_defaults --foo 3.14 --bar True
    """
    print(locals())


@atools.CLI()
def keyword_only_with_defaults(
    *,
    foo: typing.Annotated[float, 'A keyword-only foo with default. Is keyword-only in CLI.'] = 0.0,
    bar: typing.Annotated[bool, 'A keyword-only bar with default. Is keyword-only in CLI.'] = False,
) -> None:
    """Demo for CLI entrypoint with keyword-only args with defaults.

    Ex:
        python3 -m demo cli keyword_only_without_defaults
        python3 -m demo cli keyword_only_without_defaults --foo 3.14
        python3 -m demo cli keyword_only_without_defaults --bar True
        python3 -m demo cli keyword_only_without_defaults --foo 3.14 --bar True
        python3 -m demo cli keyword_only_without_defaults --foo 3.14 --bar True
    """
    print(locals())


class MetasyntacticEnum(enum.Enum):
    foo = 1
    bar = 2
    baz = 3


@atools.CLI()
def enum(
    arg: typing.Annotated[MetasyntacticEnum, 'An enum. Enter in any of the value name strings in CLI.'],
) -> None:
    """Demo for CLI entrypoint with Enum argument.

    Ex:
        python3 -m demo cli enum foo
        python3 -m demo cli enum bar
        python3 -m demo cli enum baz
    """
    print(locals())


@atools.CLI()
def optional(
    arg: typing.Annotated[typing.Optional[int | str], 'An optional. CLI arg may be any of these types or None.'],
) -> None:
    """Demo for CLI entrypoint with typing.Optional argument.

    Note: CLI can only parse Optional types that contain builtin primitives.

    Ex:
        python3 -m demo cli optional None
        python3 -m demo cli optional 42
    """
    print(f'{arg=!r}')


@atools.CLI()
def union_type(
    arg: typing.Annotated[bool | float | int | str | None, 'A union. CLI arg may be any of these types.'],
) -> None:
    """Demo for CLI entrypoint types.UnionType argument.

    Note that typing.Union (e.g. `typing.Union[int, str]`) is not the same as types.Union (e.g. `int | str`). This CLI
    handles both types of unions.

    Note: CLI can only parse Union types that contain builtin primitives.

    Ex:
        python3 -m demo cli union_type True
        python3 -m demo cli union_type 3.14
        python3 -m demo cli union_type 42
        python3 -m demo cli union_type \'42\'  # Force interpretation as a str.
        python3 -m demo cli union_type Hi!
        python3 -m demo cli union_type None
    """
    print(locals())


@atools.CLI()
def literal(
    arg: typing.Annotated[typing.Literal['foo', 'bar', 'baz'], 'A literal. CLI arg may be any of these choices.'],
) -> None:
    """Demo for CLI entrypoint with Literal argument.

    Ex:
        python3 -m demo cli literal foo
        python3 -m demo cli literal bar
        python3 -m demo cli literal baz
    """
    print(locals())


@dataclasses.dataclass(frozen=True)
class CustomType:
    data: bool | float | int | str | None | dict | list | set | tuple


@atools.CLI()
def custom_type(
    arg: typing.Annotated[
        CustomType,
        'A Custom type. CLI only construct custom types that take an instance of a builtin primitive or container.'
    ],
) -> None:
    """Demo for CLI entrypoint with CustomType argument.

    Ex:
        python3 -m demo cli custom_type True
        python3 -m demo cli custom_type 3.14
        python3 -m demo cli custom_type 42
        python3 -m demo cli custom_type Hi!
        python3 -m demo cli custom_type None
        python3 -m demo cli custom_type "{1: 2}"
        python3 -m demo cli custom_type "['foo', 'bar', 'baz']"
        python3 -m demo cli custom_type "{0.0, 1.618, 3.14}"
        python3 -m demo cli custom_type "(True, False)"
        python3 -m demo cli custom_type "(0, [1, 2], {3, 4, 5}, {6: 7, 8: 9})"
    """
    print(locals())


@atools.CLI()
def var_positional(
    *args: typing.Annotated[int | float, 'A var-positional arg. Is any remaining positional args in CLI.'],
) -> None:
    """Demo for CLI entrypoint with var-positional arguments.

    Ex:
        python3 -m demo cli var_positional 1 1 2 3 5 7
        python3 -m demo cli var_positional 0 1.618 3.14
    """
    print(locals())


@atools.CLI()
def var_keyword(
    **kwargs: typing.Annotated[int | float | str, 'A var-keyword arg. Is any remaining flag args in CLI.'],
) -> None:
    """Demo for CLI entrypoint with var-keyword arguments.

    Ex:
        python3 -m demo cli var_keyword --foo 42 --bar 3.14 --baz Hi!
    """
    print(locals())


@atools.CLI()
def _hidden_subcommand(foo: int) -> None:
    """Demo for CLI entrypoint where `_hidden_subcommand` does not show as a subcommand in help text.

    Ex:
        python3 -m demo cli --help
        python3 -m demo cli _hidden_subcommand 42
    """
    print(locals())


@atools.CLI()
def log_level_with_bound_logger(log_level: atools.CLI.Annotated.log_level(logger) = 'ERROR') -> None:
    """Demo for CLI entrypoint where bound logger has level set to parsed `log_level` value.

    Ex:
        python3 -m demo cli log_level_with_bound_logger --log-level INFO
        python3 -m demo cli log_level_with_bound_logger --log-level CRITICAL
    """
    print(locals())

    print(f'Logger level is set to {logging.getLevelName(logger.getEffectiveLevel())}')

    logger.debug('If you can see this log line, your log_level is at least DEBUG.')
    logger.info('If you can see this log line, your log_level is at least INFO.')
    logger.warning('If you can see this log line, your log_level is at least WARNING.')
    logger.error('If you can see this log line, your log_level is at least ERROR.')
    logger.fatal('If you can see this log line, your log_level is at least FATAL.')
    logger.critical('If you can see this log line, your log_level is at least CRITICAL.')


@atools.CLI()
def log_level_with_bound_logger_name(log_level: atools.CLI.Annotated.log_level(__name__) = 'ERROR') -> None:
    """Demo for CLI entrypoint where logger with bound name has level set to parsed `log_level` value.

    Ex:
        python3 -m demo cli log_level_with_bound_logger_name --log-level INFO
        python3 -m demo cli log_level_with_bound_logger_name --log-level CRITICAL
    """
    print(locals())

    print(f'Logger level is set to {logging.getLevelName(logging.getLogger(__name__).getEffectiveLevel())}')

    logging.getLogger(__name__).debug('If you can see this log line, your log_level is at least DEBUG.')
    logging.getLogger(__name__).info('If you can see this log line, your log_level is at least INFO.')
    logging.getLogger(__name__).warning('If you can see this log line, your log_level is at least WARNING.')
    logging.getLogger(__name__).error('If you can see this log line, your log_level is at least ERROR.')
    logging.getLogger(__name__).fatal('If you can see this log line, your log_level is at least FATAL.')
    logging.getLogger(__name__).critical('If you can see this log line, your log_level is at least CRITICAL.')


@atools.CLI()
def verbose_with_bound_logger(verbose: atools.CLI.Annotated.verbose(logger) = logging.DEBUG) -> None:
    """Demo for CLI entrypoint where bound logger has level set to parsed `verbose` value.

    Ex:
        python3 -m demo cli verbose_with_bound_logger
        python3 -m demo cli verbose_with_bound_logger -v
        python3 -m demo cli verbose_with_bound_logger -vvv
        python3 -m demo cli verbose_with_bound_logger -vvvvv
    """
    print(locals())

    print(f'Logger level is set to {logging.getLevelName(logger.getEffectiveLevel())}')

    logger.debug('If you can see this log line, your log_level is at least DEBUG.')
    logger.info('If you can see this log line, your log_level is at least INFO.')
    logger.warning('If you can see this log line, your log_level is at least WARNING.')
    logger.error('If you can see this log line, your log_level is at least ERROR.')
    logger.fatal('If you can see this log line, your log_level is at least FATAL.')
    logger.critical('If you can see this log line, your log_level is at least CRITICAL.')


if __name__ == '__main__':
    atools.CLI(__name__).run()
