"""Startup reconciliation of persisted world restoration history."""

from datetime import UTC, datetime

from sqlalchemy import update

from ..db.database import get_async_session
from ..logger import get_logger
from .models import Restoration, RestorationStatus


async def mark_running_restorations_interrupted() -> int:
    """Flip any RUNNING rows to INTERRUPTED on startup; returns row count."""
    logger = get_logger()
    async with get_async_session() as session:
        result = await session.execute(
            update(Restoration)
            .where(Restoration.status == RestorationStatus.RUNNING)
            .values(
                status=RestorationStatus.INTERRUPTED,
                error_message="server restarted before completion",
                finished_at=datetime.now(UTC),
            )
        )
        await session.commit()
    count = getattr(result, "rowcount", 0) or 0
    if count:
        logger.info(
            "world restore: flipped %d running restoration(s) to interrupted on startup",
            count,
        )
    return int(count)
