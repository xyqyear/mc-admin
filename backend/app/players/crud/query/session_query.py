"""Session query functions for API endpoints."""

import base64
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import Player, PlayerSession, Server
from ....server_tracker.crud import get_server_db_id


class SessionInfo(BaseModel):
    """Session information."""

    session_id: int
    server_db_id: int
    server_id: str
    joined_at: datetime
    left_at: Optional[datetime]
    duration_seconds: Optional[int]
    is_active: bool


class OnlinePlayerInfo(BaseModel):
    """Online player information."""

    player_db_id: int
    uuid: str
    current_name: str
    avatar_base64: Optional[str]
    joined_at: datetime
    session_duration_seconds: int


class SessionStatsResponse(BaseModel):
    """Session statistics response."""

    total_sessions: int
    total_playtime_seconds: int
    average_session_seconds: int
    longest_session_seconds: int
    sessions_by_server: Dict[str, int]
    playtime_by_server: Dict[str, int]


async def get_player_sessions(
    session: AsyncSession,
    player_db_id: int,
    limit: int = 100,
    server_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[SessionInfo]:
    """Get player sessions.

    Args:
        session: Database session
        player_db_id: Player database ID
        limit: Maximum number of sessions to return
        server_id: Filter by server ID
        start_date: Filter by start date
        end_date: Filter by end date

    Returns:
        List of session info
    """
    # Base query
    query = (
        select(PlayerSession, Server.server_id)
        .join(Server, PlayerSession.server_db_id == Server.id)
        .where(PlayerSession.player_db_id == player_db_id)
        .order_by(PlayerSession.joined_at.desc())
        .limit(limit)
    )

    # Apply filters
    if server_id:
        server_db_id = await get_server_db_id(session, server_id)
        if server_db_id:
            query = query.where(PlayerSession.server_db_id == server_db_id)

    if start_date:
        query = query.where(PlayerSession.joined_at >= start_date)

    if end_date:
        query = query.where(PlayerSession.joined_at <= end_date)

    result = await session.execute(query)
    rows = result.all()

    sessions = []
    for row in rows:
        player_session = row[0]
        server_id_str = row[1]

        sessions.append(
            SessionInfo(
                session_id=player_session.session_id,
                server_db_id=player_session.server_db_id,
                server_id=server_id_str,
                joined_at=player_session.joined_at,
                left_at=player_session.left_at,
                duration_seconds=player_session.duration_seconds,
                is_active=player_session.left_at is None,
            )
        )

    return sessions


async def get_server_online_players(
    session: AsyncSession, server_id: str
) -> List[OnlinePlayerInfo]:
    """Get currently online players on a server.

    Args:
        session: Database session
        server_id: Server ID

    Returns:
        List of online players
    """
    server_db_id = await get_server_db_id(session, server_id)
    if server_db_id is None:
        return []

    # Query active sessions (left_at is NULL)
    query = (
        select(PlayerSession, Player)
        .join(Player, PlayerSession.player_db_id == Player.player_db_id)
        .where(
            PlayerSession.server_db_id == server_db_id,
            PlayerSession.left_at == None,  # noqa: E711
        )
        .order_by(PlayerSession.joined_at.desc())
    )

    result = await session.execute(query)
    rows = result.all()

    now = datetime.now(timezone.utc)
    online_players = []

    for row in rows:
        player_session = row[0]
        player = row[1]

        # Calculate session duration using current time
        session_duration = int((now - player_session.joined_at).total_seconds())

        avatar_base64 = (
            base64.b64encode(player.avatar_data).decode("utf-8")
            if player.avatar_data
            else None
        )

        online_players.append(
            OnlinePlayerInfo(
                player_db_id=player.player_db_id,
                uuid=player.uuid,
                current_name=player.current_name,
                avatar_base64=avatar_base64,
                joined_at=player_session.joined_at,
                session_duration_seconds=session_duration,
            )
        )

    return online_players


async def get_player_session_stats(
    session: AsyncSession,
    player_db_id: int,
    period: str = "all",
) -> SessionStatsResponse:
    """Get player session statistics.

    Args:
        session: Database session
        player_db_id: Player database ID
        period: Time period (all, week, month, year)

    Returns:
        Session statistics
    """
    # Calculate date filter based on period
    start_date = None
    if period == "week":
        start_date = datetime.now(timezone.utc) - timedelta(days=7)
    elif period == "month":
        start_date = datetime.now(timezone.utc) - timedelta(days=30)
    elif period == "year":
        start_date = datetime.now(timezone.utc) - timedelta(days=365)

    # Base filter
    filters = [PlayerSession.player_db_id == player_db_id]
    if start_date:
        filters.append(PlayerSession.joined_at >= start_date)

    # Get total sessions
    total_sessions_result = await session.execute(
        select(func.count(PlayerSession.session_id)).where(and_(*filters))
    )
    total_sessions = total_sessions_result.scalar_one()

    # Get total playtime (only completed sessions)
    total_playtime_result = await session.execute(
        select(func.coalesce(func.sum(PlayerSession.duration_seconds), 0)).where(
            and_(*filters),
            PlayerSession.duration_seconds != None,  # noqa: E711
        )
    )
    total_playtime = total_playtime_result.scalar_one() or 0

    # Get average session length
    average_session = int(total_playtime / total_sessions) if total_sessions > 0 else 0

    # Get longest session
    longest_session_result = await session.execute(
        select(func.coalesce(func.max(PlayerSession.duration_seconds), 0)).where(
            and_(*filters)
        )
    )
    longest_session = longest_session_result.scalar_one() or 0

    # Get sessions by server
    sessions_by_server_result = await session.execute(
        select(
            Server.server_id,
            func.count(PlayerSession.session_id),
        )
        .join(Server, PlayerSession.server_db_id == Server.id)
        .where(and_(*filters))
        .group_by(Server.server_id)
    )
    sessions_by_server = {
        row.server_id: row[1] for row in sessions_by_server_result.all()
    }

    # Get playtime by server
    playtime_by_server_result = await session.execute(
        select(
            Server.server_id,
            func.coalesce(func.sum(PlayerSession.duration_seconds), 0),
        )
        .join(Server, PlayerSession.server_db_id == Server.id)
        .where(
            and_(*filters),
            PlayerSession.duration_seconds != None,  # noqa: E711
        )
        .group_by(Server.server_id)
    )
    playtime_by_server = {
        row.server_id: row[1] for row in playtime_by_server_result.all()
    }

    return SessionStatsResponse(
        total_sessions=total_sessions,
        total_playtime_seconds=total_playtime,
        average_session_seconds=average_session,
        longest_session_seconds=longest_session,
        sessions_by_server=sessions_by_server,
        playtime_by_server=playtime_by_server,
    )
