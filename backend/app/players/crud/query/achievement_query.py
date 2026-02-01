"""Achievement query functions for API endpoints."""

import base64
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import Player, PlayerAchievement, Server
from ....servers.crud import get_server_db_id


class AchievementInfo(BaseModel):
    """Achievement information."""

    achievement_id: int
    server_db_id: int
    server_id: str
    achievement_name: str
    earned_at: datetime


class PlayerAchievementRank(BaseModel):
    """Player achievement ranking."""

    player_db_id: int
    player_name: str
    avatar_base64: Optional[str]
    achievement_count: int
    recent_achievements: List[str]


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


async def get_server_achievement_leaderboard(
    session: AsyncSession,
    server_id: str,
    limit: int = 50,
) -> List[PlayerAchievementRank]:
    """Get server achievement leaderboard.

    Args:
        session: Database session
        server_id: Server ID
        limit: Number of players to return

    Returns:
        List of player achievement rankings
    """
    server_db_id = await get_server_db_id(session, server_id)
    if server_db_id is None:
        return []

    # Query to get achievement counts per player
    query = (
        select(
            Player.player_db_id,
            Player.current_name,
            Player.avatar_data,
            func.count(PlayerAchievement.achievement_id).label("achievement_count"),
        )
        .join(PlayerAchievement, Player.player_db_id == PlayerAchievement.player_db_id)
        .where(PlayerAchievement.server_db_id == server_db_id)
        .group_by(Player.player_db_id, Player.current_name, Player.avatar_data)
        .order_by(func.count(PlayerAchievement.achievement_id).desc())
        .limit(limit)
    )

    result = await session.execute(query)
    rows = result.all()

    leaderboard = []
    for row in rows:
        player_db_id = row.player_db_id
        player_name = row.current_name
        avatar_data = row.avatar_data
        achievement_count = row.achievement_count

        # Get recent 3 achievements for this player on this server
        recent_achievements_query = (
            select(PlayerAchievement.achievement_name)
            .where(
                PlayerAchievement.player_db_id == player_db_id,
                PlayerAchievement.server_db_id == server_db_id,
            )
            .order_by(PlayerAchievement.earned_at.desc())
            .limit(3)
        )
        recent_result = await session.execute(recent_achievements_query)
        recent_achievements = [row[0] for row in recent_result.all()]

        avatar_base64 = (
            base64.b64encode(avatar_data).decode("utf-8") if avatar_data else None
        )

        leaderboard.append(
            PlayerAchievementRank(
                player_db_id=player_db_id,
                player_name=player_name,
                avatar_base64=avatar_base64,
                achievement_count=achievement_count,
                recent_achievements=recent_achievements,
            )
        )

    return leaderboard
