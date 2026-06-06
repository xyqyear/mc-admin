"""Extensible notification bus for future self-check push integrations."""

from typing import Protocol

from ..logger import logger
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
            except Exception as exc:
                logger.warning("self-check notification sink failed: %s", exc)


self_check_notification_bus = SelfCheckNotificationBus()
