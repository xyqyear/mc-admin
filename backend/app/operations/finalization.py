"""Keep required cleanup owned until it has actually settled."""

import asyncio
from collections.abc import Awaitable

from anyio import CancelScope


async def finalize[T](awaitable: Awaitable[T]) -> T:
    task = asyncio.ensure_future(awaitable)
    cancelled = False
    with CancelScope(shield=True):
        while True:
            try:
                await asyncio.shield(task)
                break
            except asyncio.CancelledError:
                if task.cancelled():
                    raise
                cancelled = True
    if cancelled:
        raise asyncio.CancelledError
    return task.result()
