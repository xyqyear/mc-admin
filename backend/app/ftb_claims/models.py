from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

DetectedFormat = Literal[
    "snbt",
    "per_team_nbt",
    "universe_dat",
    "latmod_json",
]

TeamType = Literal["player", "party", "server", "unknown"]


class ClaimMember(BaseModel):
    uuid: Optional[str] = None
    name: Optional[str] = None
    rank: Optional[str] = None


class ClaimDimensionEntry(BaseModel):
    ftb_id: str
    region_dir_relpath: Optional[str] = None
    exists_on_disk: bool


class ClusterEntry(BaseModel):
    id: str
    region_dir_relpath: Optional[str] = None
    chunks: List[Tuple[int, int]]
    force_loaded: List[Tuple[int, int]]
    centroid_block: Tuple[float, float]
    bbox_chunk: Tuple[int, int, int, int]
    regions: List[Tuple[int, int]]


class TeamEntry(BaseModel):
    id: str
    display_name: str
    type: TeamType
    members: List[ClaimMember] = Field(default_factory=list)
    owner: Optional[ClaimMember] = None
    total_chunks: int
    clusters: List[ClusterEntry] = Field(default_factory=list)


class ClaimsResponse(BaseModel):
    available: bool
    detected_format: Optional[DetectedFormat] = None
    dimensions: List[ClaimDimensionEntry] = Field(default_factory=list)
    teams: List[TeamEntry] = Field(default_factory=list)
