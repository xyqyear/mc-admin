"""Player management system for MC Admin.

Tracks player activity, sessions, chat, achievements, and skins.
"""

from ..logger import log_exception, logger


@log_exception("Error starting player system: ")
async def start_player_system() -> None:
    """Start all player tracking subsystems in the correct order.

    Server enumeration is DB-driven: only servers with an ACTIVE row in the
    `Server` table are watched. Orphan filesystem directories are not
    discovered here; the operator adopts them explicitly via the sync endpoint.
    """
    from ..db.database import get_async_session
    from ..log_monitor import log_monitor
    from ..servers.crud import get_active_servers

    from .heartbeat import heartbeat_manager
    from .player_syncer import player_syncer

    # Heartbeat starts first; it owns crash recovery for the rest of the system.
    await heartbeat_manager.start()

    server_ids: list[str] = []
    try:
        async with get_async_session() as db:
            rows = await get_active_servers(db)
            server_ids = [r.server_id for r in rows]
    except Exception as e:
        logger.error(
            f"Error reading active servers for log monitoring: {e}",
            exc_info=True,
        )

    for server_id in server_ids:
        try:
            await log_monitor.start_server(server_id)
        except Exception as e:
            logger.error(
                f"Error starting log monitoring for {server_id}: {e}",
                exc_info=True,
            )

    await player_syncer.start()

    logger.info("Player monitoring system started successfully")


async def stop_player_system() -> None:
    """Stop all player tracking subsystems."""
    from ..log_monitor import log_monitor

    from .heartbeat import heartbeat_manager
    from .player_syncer import player_syncer

    logger.info("Stopping player monitoring system...")

    await player_syncer.stop()
    await log_monitor.stop_all()
    await heartbeat_manager.stop()

    logger.info("Player monitoring system stopped")
