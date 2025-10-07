"""CRUD operations for PlayerAchievement model."""

from datetime import datetime

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import PlayerAchievement


async def upsert_achievement(
    session: AsyncSession,
    player_db_id: int,
    server_db_id: int,
    achievement_name: str,
    earned_at: datetime,
) -> None:
    """Upsert achievement (avoid duplicates).

    Args:
        session: Database session
        player_db_id: Player database ID
        server_db_id: Server database ID
        achievement_name: Achievement name
        earned_at: Achievement timestamp
    """
    stmt = insert(PlayerAchievement).values(
        player_db_id=player_db_id,
        server_db_id=server_db_id,
        achievement_name=achievement_name,
        earned_at=earned_at,
    )
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["player_db_id", "server_db_id", "achievement_name"]
    )
    await session.execute(stmt)
    await session.commit()
