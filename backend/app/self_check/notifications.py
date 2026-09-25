"""Extensible notification bus for future self-check push integrations."""

from typing import Protocol

from ..errors import log_safe_error
from ..runtime_resources import current_runtime
from .types import SelfCheckRunResult


class SelfCheckNotificationSink(Protocol):
    async def publish(self, result: SelfCheckRunResult) -> None: ...


class SelfCheckNotificationBus:
    def __init__(self) -> None:
        self._sinks: list[SelfCheckNotificationSink] = []

    def register(self, sink: SelfCheckNotificationSink) -> None:
        self._sinks.append(sink)

    async def publish(self, result: SelfCheckRunResult) -> None:
        for sink in list(self._sinks):
            try:
                await sink.publish(result)
            except Exception as exc:  # noqa: BLE001 - independent sinks must not prevent delivery to each other
                log_safe_error(exc, "Self-check notification sink failed")


def get_self_check_notification_bus() -> SelfCheckNotificationBus:
    return current_runtime().resource('self_check_notifications')
