"""Event-triggered self-check helper."""


from ..dynamic_config import get_config
from ..errors import log_safe_error
from ..logger import get_logger
from ..runtime_resources import spawn_background
from .constants import (
    SERVER_CREATED_TRIGGER,
    SERVER_POPULATED_TRIGGER,
    WORLD_RESTORED_TRIGGER,
    WORLD_ROLLED_BACK_TRIGGER,
)


def _enabled_for_trigger(trigger: str) -> bool:
    logger = get_logger()
    try:
        event_config = get_config().self_check.event_triggers
    except RuntimeError:
        logger.warning("Self-check event trigger skipped: configuration unavailable")
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
        from app.self_check.service import get_self_check_service

        try:
            await get_self_check_service().run_self_check(
                trigger=trigger,
                requested_by_user_id=requested_by_user_id,
            )
        except Exception as exc:  # noqa: BLE001 - optional health work must not fail its initiating operation
            log_safe_error(exc, "Event-triggered self-check failed")

    spawn_background(_run(), name="event-self-check")
