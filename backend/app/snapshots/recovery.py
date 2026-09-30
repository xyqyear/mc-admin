"""Startup reconciliation of retained restoration history."""

from ..db.database import get_async_session
from ..logger import get_logger
from .restoration_store import RestorationStore


async def mark_running_restorations_interrupted() -> int:
    logger = get_logger()
    count = await RestorationStore(get_async_session).interrupt_running()
    if count:
        logger.info(
            "restore: marked %d unfinished restoration(s) interrupted on startup",
            count,
        )
    return int(count)
