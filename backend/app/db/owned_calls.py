import asyncio
from collections.abc import Awaitable

from anyio.lowlevel import checkpoint_if_cancelled

from ..operations.finalization import finalize


async def complete_database_call[T](awaitable: Awaitable[T]) -> T:
    try:
        result = await finalize(awaitable)
    except Exception as error:
        try:
            await checkpoint_if_cancelled()
        except asyncio.CancelledError as cancelled:
            raise cancelled from error
        raise
    await checkpoint_if_cancelled()
    return result
