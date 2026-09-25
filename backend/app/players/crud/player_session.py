"""CRUD operations for PlayerSession model."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.players.models import PlayerSession


async def get_or_create_session(
    session: AsyncSession, player_db_id: int, server_db_id: int, joined_at: datetime
) -> PlayerSession:
    """Get existing open session or create new one.

    This implements strict session management: if an open session exists,
    reuse it instead of creating a new one. This prevents duplicate open sessions.

    Args:
        session: Database session
        player_db_id: Player database ID
        server_db_id: Server database ID
        joined_at: Join timestamp

    Returns:
        Existing or newly created session
    """
    await session.execute(
        insert(PlayerSession)
        .values(
            player_db_id=player_db_id,
            server_db_id=server_db_id,
            joined_at=joined_at,
            left_at=None,
            duration_seconds=None,
        )
        .on_conflict_do_nothing(
            index_elements=[PlayerSession.player_db_id, PlayerSession.server_db_id],
            index_where=PlayerSession.left_at.is_(None),
        )
    )
    result = await session.execute(
        select(PlayerSession)
        .where(
            PlayerSession.player_db_id == player_db_id,
            PlayerSession.server_db_id == server_db_id,
            PlayerSession.left_at == None,
        )
        .order_by(PlayerSession.joined_at.desc())
    )
    player_session = result.scalar_one()
    await session.commit()
    return player_session


async def end_all_open_sessions(
    session: AsyncSession,
    player_db_id: int,
    server_db_id: int,
    left_at: datetime,
) -> int:
    """End all open sessions for player on server.

    This implements strict session management: end ALL open sessions to ensure
    eventual consistency, even if there are multiple open sessions due to edge cases.

    Args:
        session: Database session
        player_db_id: Player database ID
        server_db_id: Server database ID
        left_at: Leave timestamp

    Returns:
        Number of sessions ended
    """
    result = await session.execute(
        select(PlayerSession).where(
            PlayerSession.player_db_id == player_db_id,
            PlayerSession.server_db_id == server_db_id,
            PlayerSession.left_at == None,
        )
    )
    open_sessions = result.scalars().all()

    return await _end_sessions(session, open_sessions, left_at)


async def _end_sessions(
    session: AsyncSession, open_sessions: Sequence[PlayerSession], left_at: datetime
) -> int:
    count = 0
    for player_session in open_sessions:
        ended_at = max(left_at, player_session.joined_at)
        duration = int((ended_at - player_session.joined_at).total_seconds())
        result = await session.execute(
            update(PlayerSession)
            .where(PlayerSession.session_id == player_session.session_id, PlayerSession.left_at.is_(None))
            .values(left_at=ended_at, duration_seconds=duration)
            .returning(PlayerSession.session_id)
        )
        count += result.scalar_one_or_none() is not None
    if open_sessions:
        await session.commit()
    return count


async def get_all_open_sessions_on_server(
    session: AsyncSession, server_db_id: int
) -> list[PlayerSession]:
    """Get all open sessions on a server.

    Args:
        session: Database session
        server_db_id: Server database ID

    Returns:
        List of open sessions
    """
    result = await session.execute(
        select(PlayerSession).where(
            PlayerSession.server_db_id == server_db_id,
            PlayerSession.left_at == None,
        )
    )
    return list(result.scalars().all())


async def end_all_open_sessions_on_server(
    session: AsyncSession, server_db_id: int, left_at: datetime
) -> int:
    """End all open sessions on a server.

    Used when server is stopping to close all active sessions.

    Args:
        session: Database session
        server_db_id: Server database ID
        left_at: Leave timestamp

    Returns:
        Number of sessions ended
    """
    open_sessions = await get_all_open_sessions_on_server(session, server_db_id)

    return await _end_sessions(session, open_sessions, left_at)


async def get_online_players_with_names_grouped_by_server(
    session: AsyncSession,
) -> dict[str, list[str]]:
    """Get all online players grouped by server_id with player names.

    Used for crash recovery to get server_id -> player_names mapping.

    Args:
        session: Database session

    Returns:
        Dictionary mapping server_id to list of player names
    """
    from app.players.models import Player
    from app.servers.models import Server

    result = await session.execute(
        select(Server.server_id, Player.current_name)
        .join(PlayerSession, PlayerSession.server_db_id == Server.id)
        .join(Player, PlayerSession.player_db_id == Player.player_db_id)
        .where(PlayerSession.left_at == None)
    )

    players_by_server: dict[str, list[str]] = {}
    for server_id, player_name in result.all():
        if server_id not in players_by_server:
            players_by_server[server_id] = []
        players_by_server[server_id].append(player_name)

    return players_by_server


async def get_online_player_names_on_server(
    session: AsyncSession, server_db_id: int
) -> set[str]:
    """Get online player names on a specific server.

    Used for RCON validation to compare database state with actual server state.

    Args:
        session: Database session
        server_db_id: Server database ID

    Returns:
        Set of player names currently online
    """
    from app.players.models import Player

    result = await session.execute(
        select(Player.current_name)
        .join(PlayerSession, PlayerSession.player_db_id == Player.player_db_id)
        .where(
            PlayerSession.server_db_id == server_db_id,
            PlayerSession.left_at == None,
        )
    )

    return {name for (name,) in result.all()}
