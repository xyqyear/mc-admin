from typing import Literal

from pydantic import BaseModel, Field

DetectedFormat = Literal[
    "snbt",
    "per_team_nbt",
    "universe_dat",
    "latmod_json",
]

TeamType = Literal["player", "party", "server", "unknown"]


class ClaimMember(BaseModel):
    uuid: str | None = None
    name: str | None = None
    rank: str | None = None


class ClaimDimensionEntry(BaseModel):
    ftb_id: str
    region_dir_relpath: str | None = None
    exists_on_disk: bool


class ClusterEntry(BaseModel):
    id: str
    region_dir_relpath: str | None = None
    chunks: list[tuple[int, int]]
    force_loaded: list[tuple[int, int]]
    centroid_block: tuple[float, float]
    bbox_chunk: tuple[int, int, int, int]
    regions: list[tuple[int, int]]


class TeamEntry(BaseModel):
    id: str
    display_name: str
    type: TeamType
    members: list[ClaimMember] = Field(default_factory=list)
    owner: ClaimMember | None = None
    total_chunks: int
    clusters: list[ClusterEntry] = Field(default_factory=list)


class ClaimsResponse(BaseModel):
    available: bool
    detected_format: DetectedFormat | None = None
    dimensions: list[ClaimDimensionEntry] = Field(default_factory=list)
    teams: list[TeamEntry] = Field(default_factory=list)
