from typing import List, Literal, Optional

from pydantic import BaseModel, Field

PlayerIdKind = Literal["uuid", "name"]
PlayerStorageKind = Literal["playerdata", "players_data", "legacy_players"]
PlayerSkipReason = Literal[
    "parse_error",
    "missing_pos",
    "invalid_pos",
    "missing_dimension",
    "invalid_dimension",
]


class PlayerLocationDimensionEntry(BaseModel):
    dimension_id: str
    folder: str
    region_dir_relpath: Optional[str] = None
    exists_on_disk: bool


class PlayerLocationPosition(BaseModel):
    x: float
    y: float
    z: float


class PlayerLocationEntry(BaseModel):
    id: str
    id_kind: PlayerIdKind
    uuid: Optional[str] = None
    source: str
    storage: PlayerStorageKind
    data_version: Optional[int] = None
    dimension_id: str
    region_dir_relpath: Optional[str] = None
    pos: PlayerLocationPosition


class PlayerLocationSkippedFile(BaseModel):
    source: str
    storage: PlayerStorageKind
    reason: PlayerSkipReason
    message: Optional[str] = None


class PlayerLocationsResponse(BaseModel):
    dimensions: List[PlayerLocationDimensionEntry] = Field(default_factory=list)
    players: List[PlayerLocationEntry] = Field(default_factory=list)
    skipped: List[PlayerLocationSkippedFile] = Field(default_factory=list)
