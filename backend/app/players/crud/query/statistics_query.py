"""Statistics query functions for API endpoints."""

import base64
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import Player, PlayerOnlineStatus, PlayerSession
from ....server_tracker.crud import get_server_db_id


class GlobalPlayerStats(BaseModel):
    """Global player statistics."""

    total_players: int
    online_players: int
    active_players_today: int
    active_players_week: int
    new_players_today: int
    new_players_week: int
    total_playtime_hours: float
    average_playtime_per_player: float


class ActivityDataPoint(BaseModel):
    """Activity trend data point."""

    timestamp: datetime
    active_players: int
    new_players: int
    total_playtime_seconds: int


class TopPlayer(BaseModel):
    """Top player by playtime."""

    player_db_id: int
    player_name: str
    avatar_base64: Optional[str]
    playtime_seconds: int


class ServerPlayerStats(BaseModel):
    """Server player statistics."""

    server_id: str
    total_unique_players: int
    active_players_week: int
    average_concurrent_players: float
    peak_concurrent_players: int
    peak_time: Optional[datetime]
    top_players_by_playtime: List[TopPlayer]


async def get_global_player_stats(session: AsyncSession) -> GlobalPlayerStats:
    """Get global player statistics.

    Args:
        session: Database session

    Returns:
        Global player stats
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)

    # Total players
    total_players_result = await session.execute(
        select(func.count(Player.player_db_id))
    )
    total_players = total_players_result.scalar_one()

    # Online players
    online_players_result = await session.execute(
        select(func.count(func.distinct(PlayerOnlineStatus.player_db_id))).where(
            PlayerOnlineStatus.is_online == True  # noqa: E712
        )
    )
    online_players = online_players_result.scalar_one()

    # Active players today (had a session today)
    active_today_result = await session.execute(
        select(func.count(func.distinct(PlayerSession.player_db_id))).where(
            PlayerSession.joined_at >= today_start
        )
    )
    active_players_today = active_today_result.scalar_one()

    # Active players this week
    active_week_result = await session.execute(
        select(func.count(func.distinct(PlayerSession.player_db_id))).where(
            PlayerSession.joined_at >= week_start
        )
    )
    active_players_week = active_week_result.scalar_one()

    # New players today
    new_today_result = await session.execute(
        select(func.count(Player.player_db_id)).where(Player.created_at >= today_start)
    )
    new_players_today = new_today_result.scalar_one()

    # New players this week
    new_week_result = await session.execute(
        select(func.count(Player.player_db_id)).where(Player.created_at >= week_start)
    )
    new_players_week = new_week_result.scalar_one()

    # Total playtime (all completed sessions)
    total_playtime_result = await session.execute(
        select(func.coalesce(func.sum(PlayerSession.duration_seconds), 0)).where(
            PlayerSession.duration_seconds != None  # noqa: E711
        )
    )
    total_playtime_seconds = total_playtime_result.scalar_one() or 0
    total_playtime_hours = total_playtime_seconds / 3600

    # Average playtime per player
    average_playtime = total_playtime_hours / total_players if total_players > 0 else 0

    return GlobalPlayerStats(
        total_players=total_players,
        online_players=online_players,
        active_players_today=active_players_today,
        active_players_week=active_players_week,
        new_players_today=new_players_today,
        new_players_week=new_players_week,
        total_playtime_hours=round(total_playtime_hours, 2),
        average_playtime_per_player=round(average_playtime, 2),
    )


async def get_activity_trend(
    session: AsyncSession,
    period: str = "week",
    interval: str = "day",
) -> List[ActivityDataPoint]:
    """Get activity trend data.

    Args:
        session: Database session
        period: Time period (week, month, year)
        interval: Data interval (hour, day, week)

    Returns:
        List of activity data points
    """
    now = datetime.now(timezone.utc)

    # Determine period and interval
    if period == "week":
        days = 7
        interval_hours = 24 if interval == "day" else 1
    elif period == "month":
        days = 30
        interval_hours = 24 if interval == "day" else 168  # week
    else:  # year
        days = 365
        interval_hours = 168  # week

    start_time = now - timedelta(days=days)
    data_points = []

    # Generate data points
    current_time = start_time
    while current_time <= now:
        next_time = current_time + timedelta(hours=interval_hours)

        # Active players in this interval
        active_players_result = await session.execute(
            select(func.count(func.distinct(PlayerSession.player_db_id))).where(
                and_(
                    PlayerSession.joined_at >= current_time,
                    PlayerSession.joined_at < next_time,
                )
            )
        )
        active_players = active_players_result.scalar_one()

        # New players in this interval
        new_players_result = await session.execute(
            select(func.count(Player.player_db_id)).where(
                and_(
                    Player.created_at >= current_time,
                    Player.created_at < next_time,
                )
            )
        )
        new_players = new_players_result.scalar_one()

        # Total playtime in this interval
        playtime_result = await session.execute(
            select(func.coalesce(func.sum(PlayerSession.duration_seconds), 0)).where(
                and_(
                    PlayerSession.joined_at >= current_time,
                    PlayerSession.joined_at < next_time,
                    PlayerSession.duration_seconds != None,  # noqa: E711
                )
            )
        )
        total_playtime = playtime_result.scalar_one() or 0

        data_points.append(
            ActivityDataPoint(
                timestamp=current_time,
                active_players=active_players,
                new_players=new_players,
                total_playtime_seconds=total_playtime,
            )
        )

        current_time = next_time

    return data_points


async def get_server_player_stats(
    session: AsyncSession, server_id: str
) -> Optional[ServerPlayerStats]:
    """Get server player statistics.

    Args:
        session: Database session
        server_id: Server ID

    Returns:
        Server player stats or None
    """
    server_db_id = await get_server_db_id(session, server_id)
    if server_db_id is None:
        return None

    week_start = datetime.now(timezone.utc) - timedelta(days=7)

    # Total unique players on this server
    total_unique_result = await session.execute(
        select(func.count(func.distinct(PlayerSession.player_db_id))).where(
            PlayerSession.server_db_id == server_db_id
        )
    )
    total_unique_players = total_unique_result.scalar_one()

    # Active players this week
    active_week_result = await session.execute(
        select(func.count(func.distinct(PlayerSession.player_db_id))).where(
            PlayerSession.server_db_id == server_db_id,
            PlayerSession.joined_at >= week_start,
        )
    )
    active_players_week = active_week_result.scalar_one()

    # Calculate average concurrent players (simplified estimation)
    # This would ideally need time-series data, so we use a simple approximation
    total_sessions_result = await session.execute(
        select(func.count(PlayerSession.session_id)).where(
            PlayerSession.server_db_id == server_db_id
        )
    )
    total_sessions = total_sessions_result.scalar_one()
    average_concurrent = total_sessions / (365 * 24) if total_sessions > 0 else 0

    # Peak concurrent players (max active sessions at any point)
    # This is a simplified calculation - in production you'd want better tracking
    peak_concurrent = 0
    peak_time = None

    # Top players by playtime on this server
    top_players_query = (
        select(
            Player.player_db_id,
            Player.current_name,
            Player.avatar_data,
            func.sum(PlayerSession.duration_seconds).label("total_playtime"),
        )
        .join(PlayerSession, Player.player_db_id == PlayerSession.player_db_id)
        .where(
            PlayerSession.server_db_id == server_db_id,
            PlayerSession.duration_seconds != None,  # noqa: E711
        )
        .group_by(Player.player_db_id, Player.current_name, Player.avatar_data)
        .order_by(func.sum(PlayerSession.duration_seconds).desc())
        .limit(10)
    )

    top_players_result = await session.execute(top_players_query)
    top_players = []

    for row in top_players_result.all():
        avatar_base64 = (
            base64.b64encode(row.avatar_data).decode("utf-8")
            if row.avatar_data
            else None
        )

        top_players.append(
            TopPlayer(
                player_db_id=row.player_db_id,
                player_name=row.current_name,
                avatar_base64=avatar_base64,
                playtime_seconds=row.total_playtime,
            )
        )

    return ServerPlayerStats(
        server_id=server_id,
        total_unique_players=total_unique_players,
        active_players_week=active_players_week,
        average_concurrent_players=round(average_concurrent, 2),
        peak_concurrent_players=peak_concurrent,
        peak_time=peak_time,
        top_players_by_playtime=top_players,
    )
