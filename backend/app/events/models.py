from datetime import datetime
from typing import Literal, TypeAlias

from pydantic import BaseModel


class EventPlayer(BaseModel):
    name: str
    uuid: str
    player_db_id: int


class ChatEvent(BaseModel):
    cursor: str
    type: Literal["chat"] = "chat"
    server_id: str
    timestamp: datetime
    player: EventPlayer
    message: str


class PlayerJoinEvent(BaseModel):
    cursor: None = None
    type: Literal["player_join"] = "player_join"
    server_id: str
    timestamp: datetime
    player: EventPlayer


class PlayerLeaveEvent(BaseModel):
    cursor: None = None
    type: Literal["player_leave"] = "player_leave"
    server_id: str
    timestamp: datetime
    player: EventPlayer
    reason: str | None = None


class ServerStoppingEvent(BaseModel):
    cursor: None = None
    type: Literal["server_stopping"] = "server_stopping"
    server_id: str
    timestamp: datetime


class HeartbeatFrame(BaseModel):
    type: Literal["heartbeat"] = "heartbeat"
    timestamp: datetime


class StreamResetFrame(BaseModel):
    type: Literal["stream_reset"] = "stream_reset"
    reason: Literal["cursor_too_old", "invalid_cursor"]


PublicEventFrame: TypeAlias = (
    ChatEvent
    | PlayerJoinEvent
    | PlayerLeaveEvent
    | ServerStoppingEvent
    | HeartbeatFrame
    | StreamResetFrame
)
