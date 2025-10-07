"""CRUD operations for PlayerSession model."""
# flake8: noqa: E711

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import PlayerSession


async def create_session(
    session: AsyncSession, player_db_id: int, server_db_id: int, joined_at: datetime
) -> PlayerSession:
    """Create a new player session.

    Args:
        session: Database session
        player_db_id: Player database ID
        server_db_id: Server database ID
        joined_at: Join timestamp

    Returns:
        Created session
    """
    new_session = PlayerSession(
        player_db_id=player_db_id,
        server_db_id=server_db_id,
        joined_at=joined_at,
        left_at=None,
        duration_seconds=None,
    )
    session.add(new_session)
    await session.commit()
    return new_session


async def get_open_session(
    session: AsyncSession, player_db_id: int, server_db_id: int
) -> Optional[PlayerSession]:
    """Get open session for player on server.

    Args:
        session: Database session
        player_db_id: Player database ID
        server_db_id: Server database ID

    Returns:
        Open session or None
    """
    result = await session.execute(
        select(PlayerSession)
        .where(
            PlayerSession.player_db_id == player_db_id,
            PlayerSession.server_db_id == server_db_id,
            PlayerSession.left_at == None,
        )
        .order_by(PlayerSession.joined_at.desc())
    )
    return result.scalar_one_or_none()


async def end_session(
    session: AsyncSession,
    player_session: PlayerSession,
    left_at: datetime,
    duration_seconds: int,
) -> None:
    """End a player session.

    Args:
        session: Database session
        player_session: Session to end
        left_at: Leave timestamp
        duration_seconds: Session duration in seconds
    """
    player_session.left_at = left_at
    player_session.duration_seconds = duration_seconds
    await session.commit()


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
