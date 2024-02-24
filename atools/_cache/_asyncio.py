import asyncio
import dataclasses
import typing

from .. import _context
from .. import _cache


@dataclasses.dataclass(frozen=True, kw_only=True)
class Context[** Params, Return](_context.AsyncContext[Params, Return], ContextData[Params]):
    lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)
    memos: dict[Key, AsyncMemo] = dataclasses.field(default_factory=dict)

    async def __call__(self, return_: Return) -> None:
        ...

    async def __aenter__(self) -> typing.Self:
        ...

    async def __aexit__(self, exc_type: type[BaseException], exc_val: object, exc_tb: types.TracebackType) -> None:
        ...
