"""Base event model for all events."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .types import EventType


class BaseEvent(BaseModel):
    """Base class for all events."""

    event_type: EventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Player events from logs
class PlayerUuidDiscoveredEvent(BaseEvent):
    """Fired when player UUID is discovered from logs."""

    event_type: EventType = EventType.PLAYER_UUID_DISCOVERED
    server_id: str = Field(..., description="Server identifier")
    player_name: str = Field(..., description="Player username")
    uuid: str = Field(..., description="Player UUID (without dashes)")


class PlayerJoinedEvent(BaseEvent):
    """Fired when player joins server."""

    event_type: EventType = EventType.PLAYER_JOINED
    server_id: str = Field(..., description="Server identifier")
    player_name: str = Field(..., description="Player username")


class PlayerLeftEvent(BaseEvent):
    """Fired when player leaves server."""

    event_type: EventType = EventType.PLAYER_LEFT
    server_id: str = Field(..., description="Server identifier")
    player_name: str = Field(..., description="Player username")
    reason: str = Field(default="", description="Disconnect reason")


class PlayerChatMessageEvent(BaseEvent):
    """Fired when player sends chat message."""

    event_type: EventType = EventType.PLAYER_CHAT_MESSAGE
    server_id: str = Field(..., description="Server identifier")
    player_name: str = Field(..., description="Player username")
    message: str = Field(..., description="Chat message content")


class PlayerAchievementEvent(BaseEvent):
    """Fired when player earns achievement."""

    event_type: EventType = EventType.PLAYER_ACHIEVEMENT
    server_id: str = Field(..., description="Server identifier")
    player_name: str = Field(..., description="Player username")
    achievement_name: str = Field(..., description="Achievement name")


# Player management events
class PlayerSkinUpdateRequestedEvent(BaseEvent):
    """Fired when a player skin update is requested."""

    event_type: EventType = EventType.PLAYER_SKIN_UPDATE_REQUESTED
    player_db_id: int = Field(..., description="Player database ID")
    uuid: str = Field(..., description="Player UUID (without dashes)")
    player_name: str = Field(..., description="Player username")


# Server log events
class ServerStoppingEvent(BaseEvent):
    """Fired when server shutdown is detected in logs."""

    event_type: EventType = EventType.SERVER_STOPPING
    server_id: str = Field(..., description="Server identifier")


# System events
class SystemCrashDetectedEvent(BaseEvent):
    """Fired when system crash is detected on startup."""

    event_type: EventType = EventType.SYSTEM_CRASH_DETECTED
    crash_timestamp: datetime = Field(
        ..., description="Timestamp of the crash (last heartbeat)"
    )
    time_since_crash: float = Field(..., description="Seconds since crash")
