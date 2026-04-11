"""Data models for parsed log events.

These are simple data containers returned by LogParser and matched by LogMonitor.
They carry no dispatch logic — callers use isinstance() matching.
"""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class LogEvent(BaseModel):
    """Base class for all log events."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PlayerUuidDiscoveredEvent(LogEvent):
    """Player UUID discovered from logs."""

    server_id: str
    player_name: str
    uuid: str


class PlayerJoinedEvent(LogEvent):
    """Player joined server."""

    server_id: str
    player_name: str


class PlayerLeftEvent(LogEvent):
    """Player left server."""

    server_id: str
    player_name: str
    reason: str = ""


class PlayerChatMessageEvent(LogEvent):
    """Player sent chat message."""

    server_id: str
    player_name: str
    message: str


class PlayerAchievementEvent(LogEvent):
    """Player earned achievement."""

    server_id: str
    player_name: str
    achievement_name: str


class ServerStoppingEvent(LogEvent):
    """Server shutdown detected in logs."""

    server_id: str
