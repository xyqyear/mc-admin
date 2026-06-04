"""CRUD operations for Player model."""
# flake8: noqa: E711, E712

from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...logger import logger
from ...models import Player
from ..identity_resolver import normalize_online_uuid, resolve_player_by_name
from ..name_filters import is_ignored_player_name


async def upsert_player(session: AsyncSession, uuid: str, player_name: str) -> bool:
    """Upsert player record (insert or update name).

    Args:
        session: Database session
        uuid: Online-mode player UUID
        player_name: Player name
    """
    if is_ignored_player_name(player_name):
        logger.info(f"Skipping ignored player {player_name}")
        return False

    normalized_uuid = normalize_online_uuid(uuid)
    if normalized_uuid is None:
        logger.warning(f"Skipping player {player_name}: non-v4 UUID {uuid}")
        return False

    stmt = insert(Player).values(
        uuid=normalized_uuid,
        current_name=player_name,
        created_at=datetime.now(timezone.utc),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["uuid"],
        set_={"current_name": player_name},
    )
    await session.execute(stmt)
    await session.commit()
    return True


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


async def get_player_by_uuid(session: AsyncSession, uuid: str) -> Optional[Player]:
    """Get player by dashless UUID."""
    normalized_uuid = normalize_online_uuid(uuid)
    if normalized_uuid is None:
        return None

    result = await session.execute(select(Player).where(Player.uuid == normalized_uuid))
    return result.scalar_one_or_none()


async def get_players_by_uuids(
    session: AsyncSession, uuids: Iterable[str]
) -> dict[str, Player]:
    """Get players by normalized online UUID."""
    normalized_uuids = [
        uuid
        for uuid in {normalize_online_uuid(value) for value in uuids}
        if uuid is not None
    ]
    if not normalized_uuids:
        return {}

    players: dict[str, Player] = {}
    chunk_size = 900
    for i in range(0, len(normalized_uuids), chunk_size):
        chunk = normalized_uuids[i : i + chunk_size]
        result = await session.execute(select(Player).where(Player.uuid.in_(chunk)))
        players.update({player.uuid: player for player in result.scalars().all()})
    return players


async def get_all_player_names_with_ids(
    session: AsyncSession,
) -> list[tuple[str, int]]:
    """Get all player names with their database IDs.

    Args:
        session: Database session

    Returns:
        List of (player_name, player_db_id) tuples
    """
    result = await session.execute(
        select(Player.current_name, Player.player_db_id, Player.uuid)
    )
    return [
        (row[0], row[1])
        for row in result.all()
        if normalize_online_uuid(row[2]) is not None
    ]


async def get_or_add_player_by_name(
    session: AsyncSession,
    server_id: str,
    player_name: str,
) -> Optional[Player]:
    """Get player by name, or add if not exists by resolving an online UUID.

    Args:
        session: Database session
        server_id: Server ID used to read usercache.json
        player_name: Player name

    Returns:
        Player or None if player doesn't exist and no online UUID is available
    """
    if is_ignored_player_name(player_name):
        logger.info(f"Skipping ignored player {player_name}")
        return None

    player = await get_player_by_name(session, player_name)
    if player:
        if normalize_online_uuid(player.uuid) is None:
            logger.warning(
                f"Skipping player {player_name}: stored UUID is not online-mode"
            )
            return None
        return player

    logger.info(f"Player {player_name} not found in database, resolving identity")

    identity = await resolve_player_by_name(server_id, player_name)
    if identity is None:
        logger.warning(f"Could not resolve online UUID for player {player_name}")
        return None

    if not await upsert_player(session, identity.uuid, identity.name):
        return None

    logger.info(f"Added player {identity.name} ({identity.uuid}) to database")

    player = await get_player_by_uuid(session, identity.uuid)

    return player


async def get_player_by_db_id(
    session: AsyncSession, player_db_id: int
) -> Optional[Player]:
    """Get player by database ID.

    Args:
        session: Database session
        player_db_id: Player database ID

    Returns:
        Player or None if not found
    """
    result = await session.execute(
        select(Player).where(Player.player_db_id == player_db_id)
    )
    return result.scalar_one_or_none()


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


async def upsert_player_profile(
    session: AsyncSession,
    uuid: str,
    player_name: str,
    skin_data: Optional[bytes],
    avatar_data: Optional[bytes],
    timestamp: datetime,
) -> Optional[Player]:
    """Upsert player identity and optional cached skin data."""
    normalized_uuid = normalize_online_uuid(uuid)
    if normalized_uuid is None:
        logger.warning(f"Skipping player profile {player_name}: non-v4 UUID {uuid}")
        return None

    if is_ignored_player_name(player_name):
        logger.info(f"Skipping ignored player profile {player_name}")
        return await get_player_by_uuid(session, normalized_uuid)

    values: dict[str, object] = {
        "uuid": normalized_uuid,
        "current_name": player_name,
        "skin_data": skin_data,
        "avatar_data": avatar_data,
        "last_skin_update": timestamp if skin_data or avatar_data else None,
        "created_at": datetime.now(timezone.utc),
    }
    update_values: dict[str, object] = {"current_name": player_name}
    if skin_data is not None:
        update_values["skin_data"] = skin_data
    if avatar_data is not None:
        update_values["avatar_data"] = avatar_data
    if skin_data is not None or avatar_data is not None:
        update_values["last_skin_update"] = timestamp

    stmt = insert(Player).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["uuid"],
        set_=update_values,
    )
    await session.execute(stmt)
    await session.commit()
    return await get_player_by_uuid(session, normalized_uuid)
