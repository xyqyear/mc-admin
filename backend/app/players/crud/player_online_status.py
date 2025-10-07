"""CRUD operations for PlayerOnlineStatus model."""
# flake8: noqa: E711, E712

from datetime import datetime
from typing import List

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Player, PlayerOnlineStatus, Server


async def upsert_player_online_status(
    session: AsyncSession,
    player_db_id: int,
    server_db_id: int,
    is_online: bool,
    timestamp: datetime,
) -> None:
    """Upsert player online status.

    Args:
        session: Database session
        player_db_id: Player database ID
        server_db_id: Server database ID
        is_online: Whether player is online
        timestamp: Status update timestamp
    """
    stmt = insert(PlayerOnlineStatus).values(
        player_db_id=player_db_id,
        server_db_id=server_db_id,
        is_online=is_online,
        last_join=timestamp if is_online else None,
        last_leave=None if is_online else timestamp,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["player_db_id", "server_db_id"],
        set_={
            "is_online": is_online,
            "last_join": timestamp if is_online else PlayerOnlineStatus.last_join,
            "last_leave": None if is_online else timestamp,
        },
    )
    await session.execute(stmt)
    await session.commit()


async def set_player_offline(
    session: AsyncSession, player_db_id: int, server_db_id: int, timestamp: datetime
) -> None:
    """Set player offline.

    Args:
        session: Database session
        player_db_id: Player database ID
        server_db_id: Server database ID
        timestamp: Offline timestamp
    """
    result = await session.execute(
        select(PlayerOnlineStatus).where(
            PlayerOnlineStatus.player_db_id == player_db_id,
            PlayerOnlineStatus.server_db_id == server_db_id,
        )
    )
    status = result.scalar_one_or_none()

    if status:
        status.is_online = False
        status.last_leave = timestamp
        await session.commit()


async def set_all_players_offline_on_server(
    session: AsyncSession, server_db_id: int, timestamp: datetime
) -> int:
    """Set all players offline on a server.

    Args:
        session: Database session
        server_db_id: Server database ID
        timestamp: Offline timestamp

    Returns:
        Number of players marked offline
    """
    result = await session.execute(
        select(PlayerOnlineStatus).where(
            PlayerOnlineStatus.server_db_id == server_db_id,
            PlayerOnlineStatus.is_online == True,
        )
    )
    statuses = result.scalars().all()

    for status in statuses:
        status.is_online = False
        status.last_leave = timestamp

    await session.commit()
    return len(statuses)


async def get_online_players_on_server(
    session: AsyncSession, server_db_id: int
) -> List[tuple[PlayerOnlineStatus, Player]]:
    """Get online players on a server.

    Args:
        session: Database session
        server_db_id: Server database ID

    Returns:
        List of (PlayerOnlineStatus, Player) tuples
    """
    result = await session.execute(
        select(PlayerOnlineStatus, Player)
        .join(Player, PlayerOnlineStatus.player_db_id == Player.player_db_id)
        .where(
            PlayerOnlineStatus.server_db_id == server_db_id,
            PlayerOnlineStatus.is_online == True,
        )
    )
    rows = result.all()
    return [(status, player) for status, player in rows]


async def get_online_players_grouped_by_server(
    session: AsyncSession,
) -> dict[str, list[str]]:
    """Get all online players grouped by server_id.

    Args:
        session: Database session

    Returns:
        Dictionary mapping server_id to list of player names
    """
    # Get all online players with server information
    result = await session.execute(
        select(PlayerOnlineStatus, Player, Server)
        .join(Player, PlayerOnlineStatus.player_db_id == Player.player_db_id)
        .join(Server, PlayerOnlineStatus.server_db_id == Server.id)
        .where(PlayerOnlineStatus.is_online == True)
    )

    # Group by server_id
    players_by_server: dict[str, list[str]] = {}
    for _status, player, server in result.all():
        server_id = server.server_id
        if server_id not in players_by_server:
            players_by_server[server_id] = []
        players_by_server[server_id].append(player.current_name)

    return players_by_server
