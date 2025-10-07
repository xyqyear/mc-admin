"""CRUD operations for Player model."""
# flake8: noqa: E711, E712

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...logger import logger
from ...models import Player
from ..mojang_api import fetch_player_uuid_from_mojang


async def upsert_player(session: AsyncSession, uuid: str, player_name: str) -> None:
    """Upsert player record (insert or update name).

    Args:
        session: Database session
        uuid: Player UUID (without dashes)
        player_name: Player name
    """
    stmt = insert(Player).values(
        uuid=uuid,
        current_name=player_name,
        created_at=datetime.now(timezone.utc),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["uuid"],
        set_={"current_name": player_name},
    )
    await session.execute(stmt)
    await session.commit()


async def get_player_by_name(
    session: AsyncSession, player_name: str
) -> Optional[Player]:
    """Get player by name.

    Args:
        session: Database session
        player_name: Player name

    Returns:
        Player or None if not found
    """
    result = await session.execute(
        select(Player).where(Player.current_name == player_name)
    )
    return result.scalar_one_or_none()


async def get_or_add_player_by_name(
    session: AsyncSession,
    player_name: str,
) -> Optional[Player]:
    """Get player by name, or add if not exists by fetching UUID from Mojang.

    Args:
        session: Database session
        player_name: Player name

    Returns:
        Player or None if player doesn't exist and couldn't be fetched from Mojang
    """
    # Check if player exists
    player = await get_player_by_name(session, player_name)
    if player:
        return player

    logger.info(f"Player {player_name} not found in database, fetching from Mojang API")

    # Fetch UUID from Mojang (no database transaction during API call)
    uuid = await fetch_player_uuid_from_mojang(player_name)
    if not uuid:
        logger.warning(f"Could not fetch UUID for player {player_name}")
        return None

    # Add new player
    await upsert_player(session, uuid, player_name)

    logger.info(f"Added player {player_name} ({uuid}) to database")

    # Fetch the newly created player
    player = await get_player_by_name(session, player_name)

    return player


async def update_player_last_seen(
    session: AsyncSession, player_db_id: int, timestamp: datetime
) -> None:
    """Update player last seen timestamp.

    Args:
        session: Database session
        player_db_id: Player database ID
        timestamp: Last seen timestamp
    """
    result = await session.execute(
        select(Player).where(Player.player_db_id == player_db_id)
    )
    player = result.scalar_one_or_none()
    if player:
        player.last_seen = timestamp
        await session.commit()


async def update_player_skin(
    session: AsyncSession,
    player_db_id: int,
    skin_data: bytes,
    avatar_data: bytes,
    timestamp: datetime,
) -> None:
    """Update player skin and avatar.

    Args:
        session: Database session
        player_db_id: Player database ID
        skin_data: Skin PNG bytes
        avatar_data: Avatar PNG bytes
        timestamp: Update timestamp
    """
    result = await session.execute(
        select(Player).where(Player.player_db_id == player_db_id)
    )
    player = result.scalar_one_or_none()
    if player:
        player.skin_data = skin_data
        player.avatar_data = avatar_data
        player.last_skin_update = timestamp
        await session.commit()
