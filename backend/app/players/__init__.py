"""Player management system for MC Admin.

Tracks player activity, sessions, chat, achievements, and skins.
"""

from ..logger import log_exception, logger


@log_exception("Error starting player system: ")
async def start_player_system() -> None:
    """Start all player tracking subsystems in the correct order."""
    from ..log_monitor import log_monitor
    from ..minecraft import docker_mc_manager

    from .heartbeat import heartbeat_manager
    from .player_syncer import player_syncer

    # Start heartbeat first (includes crash detection)
    await heartbeat_manager.start()

    # Start log monitoring for existing servers
    servers = []
    try:
        servers = await docker_mc_manager.get_all_server_names()
    except Exception as e:
        logger.error(
            f"Error starting log monitoring for existing servers: {e}",
            exc_info=True,
        )

    for server_id in servers:
        try:
            await log_monitor.start_server(server_id)
        except Exception as e:
            logger.error(
                f"Error starting log monitoring for {server_id}: {e}",
                exc_info=True,
            )

    # Start RCON validation loop
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
