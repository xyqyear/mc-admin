"""Player management system for MC Admin.

Tracks player activity, sessions, chat, achievements, and skins.
"""

from ..logger import get_logger
from .service import PlayerService, get_player_service

__all__ = ["PlayerService", "get_player_service", "start_player_system", "stop_player_system"]


async def start_player_system() -> None:
    """Start all player tracking subsystems in the correct order.

    Server enumeration is DB-driven: only servers with an ACTIVE row in the
    `Server` table are watched. Orphan filesystem directories are not
    discovered here; the operator adopts them explicitly via the sync endpoint.
    """
    logger = get_logger()
    from ..db.database import get_async_session
    from ..log_monitor import get_log_monitor
    from ..servers.crud import get_active_servers
    from .heartbeat import get_heartbeat_manager
    from .player_syncer import get_player_syncer

    # Heartbeat starts first; it owns crash recovery for the rest of the system.
    await get_heartbeat_manager().start()

    server_ids: list[str] = []
    try:
        async with get_async_session() as db:
            rows = await get_active_servers(db)
            server_ids = [r.server_id for r in rows]
    except Exception:
        logger.exception(
            "Error reading active servers for log monitoring",
        )

    for server_id in server_ids:
        try:
            await get_log_monitor().start_server(server_id)
        except Exception:
            logger.exception(
                f"Error starting log monitoring for {server_id}",
                )

    await get_player_syncer().start()

    logger.info("Player monitoring system started successfully")


async def stop_player_system() -> None:
    """Stop all player tracking subsystems."""
    logger = get_logger()
    from ..log_monitor import get_log_monitor
    from .heartbeat import get_heartbeat_manager
    from .player_syncer import get_player_syncer

    logger.info("Stopping player monitoring system...")

    await get_player_syncer().stop()
    await get_log_monitor().stop_all()
    await get_heartbeat_manager().stop()

    logger.info("Player monitoring system stopped")
