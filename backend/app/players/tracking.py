"""Composite player tracking operations.

These functions combine multiple CRUD operations into logical player actions.
Called directly by LogMonitor, HeartbeatManager, PlayerSyncer, and routers.
"""

import asyncio
from datetime import datetime, timezone

from ..db.database import get_async_session
from ..logger import log_exception, logger
from ..servers.crud import get_server_db_id
from .crud import (
    create_chat_message,
    end_all_open_sessions,
    end_all_open_sessions_on_server,
    get_all_player_names_with_ids,
    get_or_add_player_by_name,
    get_player_by_name,
    get_or_create_session,
    upsert_achievement,
)
from .crud import (
    update_player_skin as crud_update_player_skin,
)
from .identity_resolver import normalize_online_uuid
from .name_filters import is_ignored_player_name
from .skin_fetcher import skin_fetcher


def _now() -> datetime:
    return datetime.now(timezone.utc)


@log_exception("Error processing player join: ")
async def process_player_join(
    server_id: str,
    player_name: str,
    timestamp: datetime | None = None,
) -> None:
    """Process a player joining a server.

    Ensures player exists in DB, creates a session, and triggers skin update.
    """
    if timestamp is None:
        timestamp = _now()

    if is_ignored_player_name(player_name):
        logger.info(f"Skipping ignored player join: {player_name}")
        return

    async with get_async_session() as session:
        player = await get_or_add_player_by_name(session, server_id, player_name)
        if player is None:
            logger.warning(f"Player not found and could not be fetched: {player_name}")
            return

        server_db_id = await get_server_db_id(session, server_id)
        if server_db_id is None:
            logger.warning(f"Server not found in database: {server_id}")
            return

        player_session = await get_or_create_session(
            session, player.player_db_id, server_db_id, timestamp
        )

        if player_session.joined_at < timestamp:
            logger.debug(f"Reused existing session for {player_name} on {server_id}")
        else:
            logger.debug(f"Created new session for {player_name} on {server_id}")

        logger.info(f"Player joined: {player_name} on {server_id}")

        player_db_id = player.player_db_id
        player_uuid = player.uuid
        player_current_name = player.current_name

    asyncio.create_task(
        update_player_skin(player_db_id, player_uuid, player_current_name)
    )


@log_exception("Error processing player left: ")
async def process_player_left(
    server_id: str,
    player_name: str,
    reason: str = "",
    timestamp: datetime | None = None,
) -> None:
    """Process a player leaving a server.

    Ensures player exists in DB and ends all open sessions.
    """
    if timestamp is None:
        timestamp = _now()

    async with get_async_session() as session:
        server_db_id = await get_server_db_id(session, server_id)
        if server_db_id is None:
            logger.warning(f"Server not found in database: {server_id}")
            return

        if is_ignored_player_name(player_name):
            player = await get_player_by_name(session, player_name)
        else:
            player = await get_or_add_player_by_name(session, server_id, player_name)
        if player is None:
            logger.warning(f"Player not found and could not be fetched: {player_name}")
            return

        count = await end_all_open_sessions(
            session, player.player_db_id, server_db_id, timestamp
        )

        if count > 0:
            logger.debug(f"Ended {count} session(s) for {player_name} on {server_id}")
        else:
            logger.warning(f"No open sessions found for {player_name} on {server_id}")

        msg = f"Player left: {player_name} from {server_id}"
        if reason:
            msg += f" ({reason})"
        logger.info(msg)


@log_exception("Error recording chat message: ")
async def record_chat_message(
    server_id: str,
    player_name: str,
    message: str,
    timestamp: datetime | None = None,
) -> None:
    """Record a player chat message."""
    if timestamp is None:
        timestamp = _now()

    if is_ignored_player_name(player_name):
        logger.info(f"Skipping ignored player chat message: {player_name}")
        return

    async with get_async_session() as session:
        server_db_id = await get_server_db_id(session, server_id)
        if server_db_id is None:
            logger.warning(f"Server not found in database: {server_id}")
            return

        player = await get_or_add_player_by_name(session, server_id, player_name)
        if player is None:
            logger.warning(f"Player not found and could not be fetched: {player_name}")
            return

        await create_chat_message(
            session, player.player_db_id, server_db_id, message, timestamp
        )

        logger.info(f"Saved chat message from {player_name} on {server_id}")


@log_exception("Error recording achievement: ")
async def record_achievement(
    server_id: str,
    player_name: str,
    achievement_name: str,
    timestamp: datetime | None = None,
) -> None:
    """Record a player achievement.

    Matches the player name in the achievement text against all known players
    (longest-first to avoid partial matches).
    """
    if timestamp is None:
        timestamp = _now()

    if is_ignored_player_name(player_name):
        logger.info(f"Skipping ignored player achievement: {player_name}")
        return

    async with get_async_session() as session:
        server_db_id = await get_server_db_id(session, server_id)
        if server_db_id is None:
            logger.warning(f"Server not found in database: {server_id}")
            return

        all_players = await get_all_player_names_with_ids(session)
        all_players_sorted = sorted(all_players, key=lambda x: len(x[0]), reverse=True)

        matched_player_db_id = None
        matched_player_name = None

        for name, player_db_id in all_players_sorted:
            if name in player_name:
                matched_player_db_id = player_db_id
                matched_player_name = name
                break

        if matched_player_db_id is None:
            logger.warning(
                f"No known player found in achievement text: '{player_name}'"
            )
            return

        logger.debug(
            f"Matched player '{matched_player_name}' in achievement text '{player_name}'"
        )

        await upsert_achievement(
            session,
            matched_player_db_id,
            server_db_id,
            achievement_name,
            timestamp,
        )

        logger.info(
            f"Saved achievement '{achievement_name}' for {matched_player_name} on {server_id}"
        )


@log_exception("Error closing server sessions: ")
async def close_server_sessions(
    server_id: str,
    timestamp: datetime | None = None,
) -> None:
    """End all open sessions on a server (e.g. when the server is stopping)."""
    if timestamp is None:
        timestamp = _now()

    async with get_async_session() as session:
        server_db_id = await get_server_db_id(session, server_id)
        if server_db_id is None:
            logger.warning(f"Server not found in database: {server_id}")
            return

        count = await end_all_open_sessions_on_server(session, server_db_id, timestamp)

        logger.info(
            f"Ended {count} session(s) for server {server_id} (server stopping)"
        )


@log_exception("Error updating player skin: ")
async def update_player_skin(
    player_db_id: int,
    uuid: str,
    player_name: str,
) -> None:
    """Fetch player skin from Mojang API and update the database."""
    normalized_uuid = normalize_online_uuid(uuid)
    if normalized_uuid is None:
        logger.warning(f"Skipping skin update for {player_name}: non-v4 UUID {uuid}")
        return

    logger.debug(f"Updating skin for player {player_name} ({normalized_uuid})")

    result = await skin_fetcher.fetch_player_skin(normalized_uuid)

    async with get_async_session() as session:
        now = _now()
        if result:
            skin_data, avatar_data = result
            await crud_update_player_skin(
                session, player_db_id, skin_data, avatar_data, now
            )
            logger.info(f"Updated skin for player {player_name}")
        else:
            logger.warning(f"Failed to fetch skin for player {player_name}")
