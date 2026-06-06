"""Event-triggered self-check helper."""

import asyncio

from ..dynamic_config import config
from ..logger import logger
from .constants import (
    SERVER_CREATED_TRIGGER,
    SERVER_POPULATED_TRIGGER,
    WORLD_RESTORED_TRIGGER,
    WORLD_ROLLED_BACK_TRIGGER,
)


def _enabled_for_trigger(trigger: str) -> bool:
    try:
        event_config = config.self_check.event_triggers
    except RuntimeError as exc:
        logger.warning("self-check event trigger skipped: %s", exc)
        return False

    return {
        SERVER_CREATED_TRIGGER: event_config.after_server_created,
        SERVER_POPULATED_TRIGGER: event_config.after_server_populated,
        WORLD_RESTORED_TRIGGER: event_config.after_world_restored,
        WORLD_ROLLED_BACK_TRIGGER: event_config.after_world_rolled_back,
    }.get(trigger, False)


def schedule_self_check_event(trigger: str, requested_by_user_id: int | None = None) -> None:
    if not _enabled_for_trigger(trigger):
        return

    async def _run() -> None:
        from .runner import run_self_check

        try:
            await run_self_check(
                trigger=trigger,
                requested_by_user_id=requested_by_user_id,
            )
        except Exception as exc:
            logger.warning("event-triggered self-check failed: %s", exc)

    asyncio.create_task(_run())
