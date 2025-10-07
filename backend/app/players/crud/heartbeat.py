"""CRUD operations for system heartbeat."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import SystemHeartbeat


async def get_heartbeat(session: AsyncSession) -> Optional[SystemHeartbeat]:
    """Get the heartbeat record.

    Args:
        session: Database session

    Returns:
        Heartbeat record or None if not found
    """
    result = await session.execute(
        select(SystemHeartbeat).where(SystemHeartbeat.id == 1)
    )
    return result.scalar_one_or_none()


async def upsert_heartbeat(
    session: AsyncSession, timestamp: datetime
) -> SystemHeartbeat:
    """Update or create the heartbeat record.

    This function ensures only one heartbeat record exists (id=1).

    Args:
        session: Database session
        timestamp: Heartbeat timestamp

    Returns:
        Updated heartbeat record
    """
    stmt = insert(SystemHeartbeat).values(
        id=1,
        timestamp=timestamp,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={"timestamp": timestamp},
    )
    await session.execute(stmt)
    await session.commit()

    # Return the updated record
    result = await session.execute(
        select(SystemHeartbeat).where(SystemHeartbeat.id == 1)
    )
    return result.scalar_one()
