"""CRUD operations for PlayerSession model."""
# flake8: noqa: E711

from datetime import datetime
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import PlayerSession


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
    # Check for existing open session
    result = await session.execute(
        select(PlayerSession)
        .where(
            PlayerSession.player_db_id == player_db_id,
            PlayerSession.server_db_id == server_db_id,
            PlayerSession.left_at == None,
        )
        .order_by(PlayerSession.joined_at.desc())
    )
    existing_session = result.scalar_one_or_none()

    if existing_session:
        # Reuse existing open session
        return existing_session

    # Create new session
    new_session = PlayerSession(
        player_db_id=player_db_id,
        server_db_id=server_db_id,
        joined_at=joined_at,
        left_at=None,
        duration_seconds=None,
    )
    session.add(new_session)
    await session.commit()
    await session.refresh(new_session)
    return new_session


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

    count = 0
    for player_session in open_sessions:
        # Calculate session duration
        duration = int((left_at - player_session.joined_at).total_seconds())
        player_session.left_at = left_at
        player_session.duration_seconds = duration
        count += 1

    if count > 0:
        await session.commit()

    return count


async def get_all_open_sessions_on_server(
    session: AsyncSession, server_db_id: int
) -> List[PlayerSession]:
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

    count = 0
    for player_session in open_sessions:
        duration = int((left_at - player_session.joined_at).total_seconds())
        player_session.left_at = left_at
        player_session.duration_seconds = duration
        count += 1

    if count > 0:
        await session.commit()

    return count


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
    from ...models import Player, Server

    result = await session.execute(
        select(Server.server_id, Player.current_name)
        .join(PlayerSession, PlayerSession.server_db_id == Server.id)
        .join(Player, PlayerSession.player_db_id == Player.player_db_id)
        .where(PlayerSession.left_at == None)  # noqa: E711
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
    from ...models import Player

    result = await session.execute(
        select(Player.current_name)
        .join(PlayerSession, PlayerSession.player_db_id == Player.player_db_id)
        .where(
            PlayerSession.server_db_id == server_db_id,
            PlayerSession.left_at == None,  # noqa: E711
        )
    )

    return {name for (name,) in result.all()}
