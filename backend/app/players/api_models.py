"""Public player map-profile payloads."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PlayerMapProfileResponse(BaseModel):
    player_db_id: int | None = None
    uuid: str
    current_name: str | None = None
    avatar_base64: str | None = None
    resolved: bool
    last_skin_update: datetime | None = None


class PlayerMapProfilesRequest(BaseModel):
    uuids: list[str] = Field(default_factory=list, max_length=2000)


class PlayerMapProfilesStreamEvent(BaseModel):
    event_type: Literal["profile", "complete", "error"]
    profile: PlayerMapProfileResponse | None = None
    message: str | None = None
    total: int | None = None
    resolved: int | None = None
