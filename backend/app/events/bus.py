from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from .models import PublicEventFrame, StreamResetFrame

DEFAULT_QUEUE_SIZE = 1000


@dataclass(eq=False)
class Subscription:
    queue: asyncio.Queue[PublicEventFrame] = field(
        default_factory=lambda: asyncio.Queue(maxsize=DEFAULT_QUEUE_SIZE)
    )
    lagged: bool = False

    def mark_lagged(self) -> None:
        if self.lagged:
            return

        self.lagged = True
        while True:
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self.queue.put_nowait(StreamResetFrame(reason="cursor_too_old"))


class EventBus:
    def __init__(self) -> None:
        self._subscriptions: set[Subscription] = set()

    def subscribe(self, maxsize: int = DEFAULT_QUEUE_SIZE) -> Subscription:
        subscription = Subscription(queue=asyncio.Queue(maxsize=maxsize))
        self._subscriptions.add(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        self._subscriptions.discard(subscription)

    def publish(self, event: PublicEventFrame) -> None:
        for subscription in list(self._subscriptions):
            if subscription.lagged:
                continue
            try:
                subscription.queue.put_nowait(event)
            except asyncio.QueueFull:
                subscription.mark_lagged()
                self.unsubscribe(subscription)

    def reset(self) -> None:
        self._subscriptions.clear()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscriptions)


event_bus = EventBus()
