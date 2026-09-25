"""Identity, session reconciliation and committed public player events."""

from collections.abc import Awaitable, Callable, Coroutine, Iterable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from ..events import (
    ChatEvent,
    EventPlayer,
    PlayerJoinEvent,
    PlayerLeaveEvent,
    PublicEventFrame,
    ServerStoppingEvent,
)
from ..logger import get_logger, log_exception
from ..runtime_resources import current_runtime
from ..servers.crud import get_server_db_id
from .crud import (
    create_chat_message,
    end_all_open_sessions,
    end_all_open_sessions_on_server,
    get_all_player_names_with_ids,
    get_online_player_names_on_server,
    get_online_players_with_names_grouped_by_server,
    get_or_create_session,
    get_player_by_name,
    get_player_by_uuid,
    upsert_achievement,
    upsert_player,
)
from .crud import (
    update_player_skin as crud_update_player_skin,
)
from .identity_resolver import (
    PlayerIdentity,
    normalize_online_uuid,
    resolve_player_by_name,
)
from .models import Player
from .name_filters import is_ignored_player_name
from .skin_fetcher import SkinFetcher


def _now() -> datetime:
    return datetime.now(UTC)


def _event_player(player_db_id: int, uuid: str, name: str) -> EventPlayer:
    return EventPlayer(player_db_id=player_db_id, uuid=uuid, name=name)


class PlayerService:
    def __init__(
        self, *,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        publish: Callable[[PublicEventFrame], None],
        spawn: Callable[[Coroutine[Any, Any, None]], object],
        skin_client: SkinFetcher,
        clock: Callable[[], datetime] = _now,
        resolve_name: Callable[[str, str], Awaitable[PlayerIdentity | None]] = resolve_player_by_name,
        ignored_name: Callable[[str], bool] = is_ignored_player_name,
    ) -> None:
        self.session_factory = session_factory
        self.publish = publish
        self.spawn = spawn
        self.skin_client = skin_client
        self.clock = clock
        self.resolve_name = resolve_name
        self.ignored_name = ignored_name

    async def ensure_player(
        self,
        session: AsyncSession,
        server_id: str,
        player_name: str,
    ) -> Player | None:
        """Get player by name, or add if not exists by resolving an online UUID.

        Args:
            session: Database session
            server_id: Server ID used to read usercache.json
            player_name: Player name

        Returns:
            Player or None if player doesn't exist and no online UUID is available
        """
        logger = get_logger()
        if self.ignored_name(player_name):
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

        identity = await self.resolve_name(server_id, player_name)
        if identity is None:
            logger.warning(f"Could not resolve online UUID for player {player_name}")
            return None

        if not await upsert_player(session, identity.uuid, identity.name, ignored_name=self.ignored_name):
            return None

        logger.info(f"Added player {identity.name} ({identity.uuid}) to database")

        player = await get_player_by_uuid(session, identity.uuid)

        return player



    @log_exception("Error discovering player identity: ")
    async def discover_identity(self, uuid: str, player_name: str) -> None:
        logger = get_logger()
        async with self.session_factory() as session:
            if await upsert_player(session, uuid, player_name, ignored_name=self.ignored_name):
                logger.info(f"Updated player UUID: {player_name} = {uuid}")

    @log_exception("Error reconciling player presence: ")
    async def reconcile_online(self, server_id: str, server_db_id: int, names: Iterable[str]) -> None:
        logger = get_logger()
        online = {name for name in names if not self.ignored_name(name)}
        async with self.session_factory() as session:
            stored = await get_online_player_names_on_server(session, server_db_id)
        for name in stored - online:
            await self.process_player_left(server_id, name)
        for name in online - stored:
            await self.process_player_join(server_id, name)
        logger.debug(
            f"Validated {server_id}: {len(online)} online, "
            f"{len(stored - online)} marked offline, {len(online - stored)} marked online"
        )

    async def recover_crash(self, timestamp: datetime) -> None:
        async with self.session_factory() as session:
            players_by_server = await get_online_players_with_names_grouped_by_server(session)
        for server_id, player_names in players_by_server.items():
            for player_name in player_names:
                await self.process_player_left(server_id, player_name, "System crash", timestamp)

    @log_exception("Error processing player join: ")
    async def process_player_join(
        self,
        server_id: str,
        player_name: str,
        timestamp: datetime | None = None,
    ) -> None:
        """Process a player joining a server.

        Ensures player exists in DB, creates a session, and triggers skin update.
        """
        logger = get_logger()
        if timestamp is None:
            timestamp = self.clock()

        if self.ignored_name(player_name):
            logger.info(f"Skipping ignored player join: {player_name}")
            return

        event: PlayerJoinEvent | None = None

        async with self.session_factory() as session:
            player = await self.ensure_player(session, server_id, player_name)
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
            event = PlayerJoinEvent(
                server_id=server_id,
                timestamp=timestamp,
                player=_event_player(player_db_id, player_uuid, player_current_name),
            )

        if event is not None:
            self.publish(event)

        self.spawn(self.update_player_skin(player_db_id, player_uuid, player_current_name))


    @log_exception("Error processing player left: ")
    async def process_player_left(
        self,
        server_id: str,
        player_name: str,
        reason: str = "",
        timestamp: datetime | None = None,
    ) -> None:
        """Process a player leaving a server.

        Ensures player exists in DB and ends all open sessions.
        """
        logger = get_logger()
        if timestamp is None:
            timestamp = self.clock()

        event: PlayerLeaveEvent | None = None

        async with self.session_factory() as session:
            server_db_id = await get_server_db_id(session, server_id)
            if server_db_id is None:
                logger.warning(f"Server not found in database: {server_id}")
                return

            if self.ignored_name(player_name):
                player = await get_player_by_name(session, player_name)
            else:
                player = await self.ensure_player(session, server_id, player_name)
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
            event = PlayerLeaveEvent(
                server_id=server_id,
                timestamp=timestamp,
                player=_event_player(
                    player.player_db_id,
                    player.uuid,
                    player.current_name,
                ),
                reason=reason or None,
            )

        if event is not None:
            self.publish(event)


    @log_exception("Error recording chat message: ")
    async def record_chat_message(
        self,
        server_id: str,
        player_name: str,
        message: str,
        timestamp: datetime | None = None,
    ) -> None:
        """Record a player chat message."""
        logger = get_logger()
        if timestamp is None:
            timestamp = self.clock()

        if self.ignored_name(player_name):
            logger.info(f"Skipping ignored player chat message: {player_name}")
            return

        event: ChatEvent | None = None

        async with self.session_factory() as session:
            server_db_id = await get_server_db_id(session, server_id)
            if server_db_id is None:
                logger.warning(f"Server not found in database: {server_id}")
                return

            player = await self.ensure_player(session, server_id, player_name)
            if player is None:
                logger.warning(f"Player not found and could not be fetched: {player_name}")
                return

            message_row = await create_chat_message(
                session, player.player_db_id, server_db_id, message, timestamp
            )

            logger.info(f"Saved chat message from {player_name} on {server_id}")
            event = ChatEvent(
                cursor=str(message_row.message_id),
                server_id=server_id,
                timestamp=timestamp,
                player=_event_player(
                    player.player_db_id,
                    player.uuid,
                    player.current_name,
                ),
                message=message,
            )

        if event is not None:
            self.publish(event)


    @log_exception("Error recording achievement: ")
    async def record_achievement(
        self,
        server_id: str,
        player_name: str,
        achievement_name: str,
        timestamp: datetime | None = None,
    ) -> None:
        """Record a player achievement.

        Matches the player name in the achievement text against all known players
        (longest-first to avoid partial matches).
        """
        logger = get_logger()
        if timestamp is None:
            timestamp = self.clock()

        if self.ignored_name(player_name):
            logger.info(f"Skipping ignored player achievement: {player_name}")
            return

        async with self.session_factory() as session:
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
        self,
        server_id: str,
        timestamp: datetime | None = None,
    ) -> None:
        """End all open sessions on a server (e.g. when the server is stopping)."""
        logger = get_logger()
        if timestamp is None:
            timestamp = self.clock()

        event: ServerStoppingEvent | None = None

        async with self.session_factory() as session:
            server_db_id = await get_server_db_id(session, server_id)
            if server_db_id is None:
                logger.warning(f"Server not found in database: {server_id}")
                return

            count = await end_all_open_sessions_on_server(session, server_db_id, timestamp)

            logger.info(
                f"Ended {count} session(s) for server {server_id} (server stopping)"
            )
            event = ServerStoppingEvent(server_id=server_id, timestamp=timestamp)

        if event is not None:
            self.publish(event)


    @log_exception("Error updating player skin: ")
    async def update_player_skin(
        self,
        player_db_id: int,
        uuid: str,
        player_name: str,
    ) -> None:
        """Fetch player skin from Mojang API and update the database."""
        logger = get_logger()
        normalized_uuid = normalize_online_uuid(uuid)
        if normalized_uuid is None:
            logger.warning(f"Skipping skin update for {player_name}: non-v4 UUID {uuid}")
            return

        logger.debug(f"Updating skin for player {player_name} ({normalized_uuid})")

        result = await self.skin_client.fetch_player_skin(normalized_uuid)

        async with self.session_factory() as session:
            now = self.clock()
            if result:
                skin_data, avatar_data = result
                await crud_update_player_skin(
                    session, player_db_id, skin_data, avatar_data, now
                )
                logger.info(f"Updated skin for player {player_name}")
            else:
                logger.warning(f"Failed to fetch skin for player {player_name}")


def get_player_service() -> PlayerService:
    return cast(PlayerService, current_runtime().resource("player_service"))
