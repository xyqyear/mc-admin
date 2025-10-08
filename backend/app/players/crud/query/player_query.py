"""Player query functions for API endpoints."""

import base64
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import Player, PlayerOnlineStatus, PlayerSession, Server
from ....server_tracker.crud import get_server_db_id


class PlayerSummary(BaseModel):
    """Player summary for list view."""

    player_db_id: int
    uuid: str
    current_name: str
    avatar_base64: Optional[str]
    is_online: bool
    last_seen: Optional[datetime]
    total_playtime_seconds: int
    first_seen: datetime


class PlayerDetailResponse(BaseModel):
    """Player detail response."""

    player_db_id: int
    uuid: str
    current_name: str
    skin_base64: Optional[str]
    avatar_base64: Optional[str]
    is_online: bool
    current_servers: List[str]
    last_seen: Optional[datetime]
    first_seen: datetime
    total_playtime_seconds: int
    total_sessions: int
    total_messages: int
    total_achievements: int


async def get_all_players_summary(
    session: AsyncSession,
    online_only: bool = False,
    server_id: Optional[str] = None,
) -> List[PlayerSummary]:
    """Get all players summary.

    Args:
        session: Database session
        online_only: Only return online players
        server_id: Filter by server ID

    Returns:
        List of player summaries
    """
    # Base query with total playtime aggregation
    query = (
        select(
            Player.player_db_id,
            Player.uuid,
            Player.current_name,
            Player.avatar_data,
            Player.last_seen,
            Player.created_at,
            func.coalesce(func.sum(PlayerSession.duration_seconds), 0).label(
                "total_playtime"
            ),
        )
        .outerjoin(PlayerSession, Player.player_db_id == PlayerSession.player_db_id)
        .group_by(
            Player.player_db_id,
            Player.uuid,
            Player.current_name,
            Player.avatar_data,
            Player.last_seen,
            Player.created_at,
        )
    )

    # Get server_db_id if server_id is provided
    server_db_id = None
    if server_id:
        server_db_id = await get_server_db_id(session, server_id)
        if server_db_id is None:
            return []

    # Check online status
    online_status_query = select(PlayerOnlineStatus).where(
        PlayerOnlineStatus.is_online == True  # noqa: E712
    )
    if server_db_id:
        online_status_query = online_status_query.where(
            PlayerOnlineStatus.server_db_id == server_db_id
        )

    online_status_result = await session.execute(online_status_query)
    online_player_ids = {
        status.player_db_id for status in online_status_result.scalars().all()
    }

    # Apply filters
    if online_only:
        query = query.where(Player.player_db_id.in_(online_player_ids))
    elif server_db_id:
        # Filter players who have sessions on this server
        query = query.where(PlayerSession.server_db_id == server_db_id)

    result = await session.execute(query)
    rows = result.all()

    players = []
    for row in rows:
        avatar_base64 = (
            base64.b64encode(row.avatar_data).decode("utf-8")
            if row.avatar_data
            else None
        )

        players.append(
            PlayerSummary(
                player_db_id=row.player_db_id,
                uuid=row.uuid,
                current_name=row.current_name,
                avatar_base64=avatar_base64,
                is_online=row.player_db_id in online_player_ids,
                last_seen=row.last_seen,
                total_playtime_seconds=row.total_playtime,
                first_seen=row.created_at,
            )
        )

    return players


async def get_player_detail_by_uuid(
    session: AsyncSession, uuid: str
) -> Optional[PlayerDetailResponse]:
    """Get player detail by UUID.

    Args:
        session: Database session
        uuid: Player UUID

    Returns:
        Player detail or None
    """
    player = await session.execute(select(Player).where(Player.uuid == uuid))
    player_obj = player.scalar_one_or_none()

    if not player_obj:
        return None

    return await _build_player_detail(session, player_obj)


async def get_player_detail_by_name(
    session: AsyncSession, name: str
) -> Optional[PlayerDetailResponse]:
    """Get player detail by name.

    Args:
        session: Database session
        name: Player name

    Returns:
        Player detail or None
    """
    player = await session.execute(select(Player).where(Player.current_name == name))
    player_obj = player.scalar_one_or_none()

    if not player_obj:
        return None

    return await _build_player_detail(session, player_obj)


async def _build_player_detail(
    session: AsyncSession, player: Player
) -> PlayerDetailResponse:
    """Build player detail response.

    Args:
        session: Database session
        player: Player object

    Returns:
        Player detail response
    """
    from ....models import PlayerAchievement, PlayerChatMessage

    # Get total playtime
    playtime_result = await session.execute(
        select(func.coalesce(func.sum(PlayerSession.duration_seconds), 0)).where(
            PlayerSession.player_db_id == player.player_db_id
        )
    )
    total_playtime = playtime_result.scalar_one() or 0

    # Get total sessions
    sessions_result = await session.execute(
        select(func.count(PlayerSession.session_id)).where(
            PlayerSession.player_db_id == player.player_db_id
        )
    )
    total_sessions = sessions_result.scalar_one()

    # Get total messages
    messages_result = await session.execute(
        select(func.count(PlayerChatMessage.message_id)).where(
            PlayerChatMessage.player_db_id == player.player_db_id
        )
    )
    total_messages = messages_result.scalar_one()

    # Get total achievements
    achievements_result = await session.execute(
        select(func.count(PlayerAchievement.achievement_id)).where(
            PlayerAchievement.player_db_id == player.player_db_id
        )
    )
    total_achievements = achievements_result.scalar_one()

    # Get current servers (where player is online)
    online_status_result = await session.execute(
        select(PlayerOnlineStatus, Server.server_id)
        .join(Server, PlayerOnlineStatus.server_db_id == Server.id)
        .where(
            PlayerOnlineStatus.player_db_id == player.player_db_id,
            PlayerOnlineStatus.is_online == True,  # noqa: E712
        )
    )
    current_servers = [row.server_id for row in online_status_result.all()]

    # Check if player is online
    is_online = len(current_servers) > 0

    # Convert skin and avatar to base64
    skin_base64 = (
        base64.b64encode(player.skin_data).decode("utf-8") if player.skin_data else None
    )
    avatar_base64 = (
        base64.b64encode(player.avatar_data).decode("utf-8")
        if player.avatar_data
        else None
    )

    return PlayerDetailResponse(
        player_db_id=player.player_db_id,
        uuid=player.uuid,
        current_name=player.current_name,
        skin_base64=skin_base64,
        avatar_base64=avatar_base64,
        is_online=is_online,
        current_servers=current_servers,
        last_seen=player.last_seen,
        first_seen=player.created_at,
        total_playtime_seconds=total_playtime,
        total_sessions=total_sessions,
        total_messages=total_messages,
        total_achievements=total_achievements,
    )
