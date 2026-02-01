"""Event dispatcher - dispatches typed events to registered handlers.

This is a simple event system without persistence.
Each event type has its own handler function with proper typing.
"""

import asyncio
from typing import Awaitable, Callable, Dict, List, TypeVar, Union

from ..logger import logger
from .base import (
    BaseEvent,
    PlayerAchievementEvent,
    PlayerChatMessageEvent,
    PlayerJoinedEvent,
    PlayerLeftEvent,
    PlayerSkinUpdateRequestedEvent,
    PlayerUuidDiscoveredEvent,
    ServerStoppingEvent,
    SystemCrashDetectedEvent,
)
from .types import EventType

# Generic type variable for event types
EventT = TypeVar("EventT", bound=BaseEvent)

# Generic handler type that can be sync or async for any event type
EventHandler = Union[Callable[[EventT], None], Callable[[EventT], Awaitable[None]]]


class EventDispatcher:
    """Dispatches events to registered handlers.

    Each event type has specific handler functions with proper typing.
    Handlers are called asynchronously.
    """

    def __init__(self):
        """Initialize event dispatcher."""
        # Each event type maps to a list of handler functions
        self._handlers: Dict[EventType, List[Callable]] = {
            event_type: [] for event_type in EventType
        }

    # Registration methods - one per event type for type safety

    def on_player_uuid_discovered(
        self, handler: EventHandler[PlayerUuidDiscoveredEvent]
    ) -> None:
        """Register handler for player UUID discovered events."""
        self._handlers[EventType.PLAYER_UUID_DISCOVERED].append(handler)

    def on_player_joined(self, handler: EventHandler[PlayerJoinedEvent]) -> None:
        """Register handler for player joined events."""
        self._handlers[EventType.PLAYER_JOINED].append(handler)

    def on_player_left(self, handler: EventHandler[PlayerLeftEvent]) -> None:
        """Register handler for player left events."""
        self._handlers[EventType.PLAYER_LEFT].append(handler)

    def on_player_chat_message(
        self, handler: EventHandler[PlayerChatMessageEvent]
    ) -> None:
        """Register handler for player chat message events."""
        self._handlers[EventType.PLAYER_CHAT_MESSAGE].append(handler)

    def on_player_achievement(
        self, handler: EventHandler[PlayerAchievementEvent]
    ) -> None:
        """Register handler for player achievement events."""
        self._handlers[EventType.PLAYER_ACHIEVEMENT].append(handler)

    def on_player_skin_update_requested(
        self, handler: EventHandler[PlayerSkinUpdateRequestedEvent]
    ) -> None:
        """Register handler for player skin update requested events."""
        self._handlers[EventType.PLAYER_SKIN_UPDATE_REQUESTED].append(handler)

    def on_server_stopping(self, handler: EventHandler[ServerStoppingEvent]) -> None:
        """Register handler for server stopping events."""
        self._handlers[EventType.SERVER_STOPPING].append(handler)

    def on_system_crash_detected(
        self, handler: EventHandler[SystemCrashDetectedEvent]
    ) -> None:
        """Register handler for system crash detected events."""
        self._handlers[EventType.SYSTEM_CRASH_DETECTED].append(handler)

    # Dispatch methods - one per event type for type safety

    async def dispatch_player_uuid_discovered(
        self, event: PlayerUuidDiscoveredEvent
    ) -> None:
        """Dispatch player UUID discovered event."""
        await self._dispatch_event(event)

    async def dispatch_player_joined(self, event: PlayerJoinedEvent) -> None:
        """Dispatch player joined event."""
        await self._dispatch_event(event)

    async def dispatch_player_left(self, event: PlayerLeftEvent) -> None:
        """Dispatch player left event."""
        await self._dispatch_event(event)

    async def dispatch_player_chat_message(self, event: PlayerChatMessageEvent) -> None:
        """Dispatch player chat message event."""
        await self._dispatch_event(event)

    async def dispatch_player_achievement(self, event: PlayerAchievementEvent) -> None:
        """Dispatch player achievement event."""
        await self._dispatch_event(event)

    async def dispatch_player_skin_update_requested(
        self, event: PlayerSkinUpdateRequestedEvent
    ) -> None:
        """Dispatch player skin update requested event."""
        await self._dispatch_event(event)

    async def dispatch_server_stopping(self, event: ServerStoppingEvent) -> None:
        """Dispatch server stopping event."""
        await self._dispatch_event(event)

    async def dispatch_system_crash_detected(
        self, event: SystemCrashDetectedEvent
    ) -> None:
        """Dispatch system crash detected event."""
        await self._dispatch_event(event)

    # Internal dispatch logic

    async def _dispatch_event(self, event: BaseEvent) -> None:
        """Dispatch event to all registered handlers.

        Args:
            event: Event to dispatch
        """
        handlers = self._handlers.get(event.event_type, [])

        if not handlers:
            logger.debug(f"No handlers registered for event: {event.event_type}")
            return

        # Call all handlers concurrently
        tasks = []
        for handler in handlers:
            try:
                # Support both async and sync handlers
                if asyncio.iscoroutinefunction(handler):
                    tasks.append(asyncio.create_task(handler(event)))
                else:
                    # Wrap sync handler in async
                    tasks.append(asyncio.create_task(asyncio.to_thread(handler, event)))
            except Exception as e:
                logger.error(
                    f"Error creating task for handler {handler.__name__}: {e}",
                    exc_info=True,
                )

        # Wait for all handlers to complete
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    handler_name = handlers[i].__name__
                    logger.error(
                        f"Handler {handler_name} failed for event {event.event_type}: {result}",
                        exc_info=result,
                    )


# Global event dispatcher instance
event_dispatcher = EventDispatcher()
