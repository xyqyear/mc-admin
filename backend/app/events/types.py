"""Event type definitions."""

from enum import Enum


class EventType(str, Enum):
    """All event types in the system."""

    # Server lifecycle events
    SERVER_CREATED = "server.created"
    SERVER_STARTED = "server.started"
    SERVER_STOPPED = "server.stopped"
    SERVER_REMOVED = "server.removed"

    # Player events from logs
    PLAYER_UUID_DISCOVERED = "player.uuid_discovered"
    PLAYER_JOINED = "player.joined"
    PLAYER_LEFT = "player.left"
    PLAYER_CHAT_MESSAGE = "player.chat_message"
    PLAYER_ACHIEVEMENT = "player.achievement"

    # Player management events
    PLAYER_SKIN_UPDATE_REQUESTED = "player.skin_update_requested"

    # Server log events
    SERVER_STOPPING = "server.stopping"

    # System events
    SYSTEM_CRASH_DETECTED = "system.crash_detected"
