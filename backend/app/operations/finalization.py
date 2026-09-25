"""Keep required cleanup owned until it has actually settled."""

import asyncio
from collections.abc import Awaitable

from anyio import CancelScope


async def finalize[T](awaitable: Awaitable[T]) -> T:
    task = asyncio.ensure_future(awaitable)
    cancelled: asyncio.CancelledError | None = None
    with CancelScope(shield=True):
        while True:
            try:
                await asyncio.shield(task)
                break
            except asyncio.CancelledError as error:
                if task.cancelled():
                    raise
                if cancelled is None:
                    cancelled = error
            except Exception as error:
                if cancelled is not None:
                    raise cancelled from error
                raise
    if cancelled is not None:
        raise cancelled
    return task.result()
