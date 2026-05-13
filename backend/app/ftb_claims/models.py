"""Pydantic response models for the FTB claims feature.

These mirror the shape returned by ``GET /servers/{id}/world-restore/claims``.
``ClaimsResponse.available`` is ``False`` when mcmap cannot detect any FTB
claim format in the world directory; in that case all list fields are empty.
"""

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
    """One FTB dimension mapped onto the backend's world layout.

    ``region_dir_relpath`` and ``label`` are filled when the dim resolves to a
    real on-disk dimension under the world root; otherwise both stay ``None``
    (e.g. when the FTB data references a dimension whose region/ folder has no
    ``.mca`` files).
    """

    ftb_id: str
    region_dir_relpath: Optional[str] = None
    label: Optional[str] = None
    exists_on_disk: bool


class ClusterEntry(BaseModel):
    """A connected component of chunks owned by a single team in a single dim.

    ``id`` is stable across reloads for the same input. ``regions`` deduplicates
    the regions touched by the cluster's chunks; ``centroid_block`` is in block
    space (suitable for ``L.Map.panTo`` after converting block-x/z to
    Leaflet CRS.Simple lat/lng).
    """

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
