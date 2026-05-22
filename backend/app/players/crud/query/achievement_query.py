"""Achievement query functions for API endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import PlayerAchievement, Server
from ....servers.crud import get_server_db_id


class AchievementInfo(BaseModel):
    """Achievement information."""

    achievement_id: int
    server_db_id: int
    server_id: str
    achievement_name: str
    earned_at: datetime


async def get_player_achievements(
    session: AsyncSession,
    player_db_id: int,
    server_id: Optional[str] = None,
) -> List[AchievementInfo]:
    """Get player achievements.

    Args:
        session: Database session
        player_db_id: Player database ID
        server_id: Filter by server ID

    Returns:
        List of achievements
    """
    # Base query
    query = (
        select(PlayerAchievement, Server.server_id)
        .join(Server, PlayerAchievement.server_db_id == Server.id)
        .where(PlayerAchievement.player_db_id == player_db_id)
        .order_by(PlayerAchievement.earned_at.desc())
    )

    # Apply server filter
    if server_id:
        server_db_id = await get_server_db_id(session, server_id)
        if server_db_id:
            query = query.where(PlayerAchievement.server_db_id == server_db_id)

    result = await session.execute(query)
    rows = result.all()

    achievements = []
    for row in rows:
        achievement = row[0]
        server_id_str = row[1]

        achievements.append(
            AchievementInfo(
                achievement_id=achievement.achievement_id,
                server_db_id=achievement.server_db_id,
                server_id=server_id_str,
                achievement_name=achievement.achievement_name,
                earned_at=achievement.earned_at,
            )
        )

    return achievements
