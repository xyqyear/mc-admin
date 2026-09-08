"""Typed JSON events emitted by the mcmap CLI."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class MCMapProtocolError(Exception):
    pass


class MCMapEventModel(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)


class MCMapProgressEvent(MCMapEventModel):
    type: Literal["progress"]
    phase: str
    elapsed_ms: int | None = None
    count: int | None = None
    bytes: int | None = None
    total: int | None = None
    index: int | None = None
    path: str | None = None


class MCMapErrorEvent(MCMapEventModel):
    type: Literal["error"]
    message: str


class MCMapGenericResultEvent(MCMapEventModel):
    type: Literal["result"]


class MCMapRenderRegionEvent(MCMapEventModel):
    type: Literal["region"]
    x: int
    z: int
    status: Literal["rendered", "missing", "error"]
    output: str | None = None
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)


class MCMapRenderResultEvent(MCMapEventModel):
    type: Literal["result"]
    mode: Literal["split", "combined"]
    regions_saved: int
    output: str
    elapsed_ms: int


class MCMapDownloadClientResultEvent(MCMapEventModel):
    type: Literal["result"]
    version: str
    target: str
    bytes: int
    sha1: str
    move_method: Literal["rename", "copy_fallback"]


class MCMapGenPaletteResultEvent(MCMapEventModel):
    type: Literal["result"]
    output: str
    entries: int
    counters: dict[str, Any]
    failed: int | None = None


class MCMapChunkReplaceEvent(MCMapEventModel):
    type: Literal["chunk_replaced"]
    x: int
    z: int
    source_kind: Literal["empty", "inline", "external"]


class MCMapChunkRemoveEvent(MCMapEventModel):
    type: Literal["chunk_removed"]
    x: int
    z: int


class MCMapReplaceChunksResultEvent(MCMapEventModel):
    type: Literal["result"]
    replaced: int


class MCMapRemoveChunksResultEvent(MCMapEventModel):
    type: Literal["result"]
    removed: int


MCMapPruneMode = Literal["chunks", "regions"]


class MCMapPruneRegionDirEvent(MCMapEventModel):
    type: Literal["region_dir"]
    path: str
    regions: int


class MCMapPruneProgressEvent(MCMapEventModel):
    type: Literal["progress"]
    phase: Literal["scan", "prune"] | str
    regions_processed: int
    regions_total: int


class MCMapPrunedChunk(MCMapEventModel):
    chunk_x: int
    chunk_z: int
    rel_x: int
    rel_z: int
    inhabited_time: int


class MCMapChunksPrunedEvent(MCMapEventModel):
    type: Literal["chunks_pruned"]
    region: str
    region_x: int
    region_z: int
    chunks: list[MCMapPrunedChunk]
    dry_run: bool


class MCMapRegionPrunedEvent(MCMapEventModel):
    type: Literal["region_pruned"]
    region: str
    region_x: int
    region_z: int
    chunks: int
    max_inhabited_time: int
    dry_run: bool


class MCMapPruneResultEvent(MCMapEventModel):
    type: Literal["result"]
    mode: MCMapPruneMode
    dry_run: bool
    region_dirs: int
    regions_scanned: int
    chunks_scanned: int
    chunks_selected: int
    regions_selected: int
    claims_loaded: int | None = None
    claimed_chunks_protected: int | None = None
    chunks_skipped_by_claims: int | None = None
    regions_skipped_by_claims: int | None = None


MCMapDetectedFtbFormat = Literal[
    "snbt",
    "per_team_nbt",
    "universe_dat",
    "latmod_json",
]

MCMapFtbTeamType = Literal["player", "party", "server", "unknown"]
MCMapPlayerIdKind = Literal["uuid", "name"]
MCMapPlayerStorageKind = Literal[
    "playerdata", "players_data", "legacy_players"
]
MCMapPlayerSkipReason = Literal[
    "parse_error",
    "missing_pos",
    "invalid_pos",
    "missing_dimension",
    "invalid_dimension",
]


class MCMapDimensionEntry(MCMapEventModel):
    id: str
    folder: str
    exists: bool


class MCMapFtbMember(MCMapEventModel):
    uuid: str | None = None
    name: str | None = None
    rank: str | None = None


class MCMapFtbClaim(MCMapEventModel):
    dim: str
    cx: int
    cz: int
    force_loaded: bool


class MCMapFtbTeam(MCMapEventModel):
    id: str
    name: str | None = None
    type: MCMapFtbTeamType
    owner: MCMapFtbMember | None = None
    members: list[MCMapFtbMember]
    claims: list[MCMapFtbClaim]


class MCMapFtbClaimsPayload(MCMapEventModel):
    mcmap_extract_ftb_claims_version: int
    detected_format: MCMapDetectedFtbFormat
    world_dir: str
    dimensions: list[MCMapDimensionEntry]
    teams: list[MCMapFtbTeam]


class MCMapFtbClaimsResultEvent(MCMapEventModel):
    type: Literal["result"]
    detected_format: MCMapDetectedFtbFormat
    teams: int
    claims: int
    dimensions: int
    output: str | None = None
    data: MCMapFtbClaimsPayload


class MCMapPlayerPosition(MCMapEventModel):
    x: float
    y: float
    z: float


class MCMapPlayerRecord(MCMapEventModel):
    id: str
    id_kind: MCMapPlayerIdKind
    source: str
    storage: MCMapPlayerStorageKind
    data_version: int | None = None
    dim: str
    pos: MCMapPlayerPosition


class MCMapSkippedPlayerFile(MCMapEventModel):
    source: str
    storage: MCMapPlayerStorageKind
    reason: MCMapPlayerSkipReason
    message: str | None = None


class MCMapPlayersPayload(MCMapEventModel):
    mcmap_extract_players_version: int
    world_dir: str
    dimensions: list[MCMapDimensionEntry]
    players: list[MCMapPlayerRecord]
    skipped: list[MCMapSkippedPlayerFile]


class MCMapPlayersResultEvent(MCMapEventModel):
    type: Literal["result"]
    players: int
    skipped: int
    dimensions: int
    output: str | None = None
    data: MCMapPlayersPayload


MCMapGenericEvent = Annotated[
    MCMapProgressEvent
    | MCMapRenderRegionEvent
    | MCMapGenericResultEvent
    | MCMapErrorEvent
    | MCMapChunkReplaceEvent
    | MCMapChunkRemoveEvent,
    Field(discriminator="type"),
]
MCMapRenderEvent = Annotated[
    MCMapProgressEvent
    | MCMapRenderRegionEvent
    | MCMapRenderResultEvent
    | MCMapErrorEvent,
    Field(discriminator="type"),
]
MCMapDownloadClientEvent = Annotated[
    MCMapProgressEvent | MCMapDownloadClientResultEvent | MCMapErrorEvent,
    Field(discriminator="type"),
]
MCMapGenPaletteEvent = Annotated[
    MCMapProgressEvent | MCMapGenPaletteResultEvent | MCMapErrorEvent,
    Field(discriminator="type"),
]
MCMapReplaceChunksEvent = Annotated[
    MCMapChunkReplaceEvent | MCMapReplaceChunksResultEvent | MCMapErrorEvent,
    Field(discriminator="type"),
]
MCMapRemoveChunksEvent = Annotated[
    MCMapChunkRemoveEvent | MCMapRemoveChunksResultEvent | MCMapErrorEvent,
    Field(discriminator="type"),
]
MCMapFtbClaimsEvent = Annotated[
    MCMapFtbClaimsResultEvent | MCMapErrorEvent,
    Field(discriminator="type"),
]
MCMapPlayersEvent = Annotated[
    MCMapPlayersResultEvent | MCMapErrorEvent,
    Field(discriminator="type"),
]
MCMapPruneEvent = Annotated[
    MCMapPruneRegionDirEvent
    | MCMapPruneProgressEvent
    | MCMapChunksPrunedEvent
    | MCMapRegionPrunedEvent
    | MCMapPruneResultEvent
    | MCMapErrorEvent,
    Field(discriminator="type"),
]

MCMAP_GENERIC_EVENT_ADAPTER = TypeAdapter(MCMapGenericEvent)
MCMAP_RENDER_EVENT_ADAPTER = TypeAdapter(MCMapRenderEvent)
MCMAP_DOWNLOAD_CLIENT_EVENT_ADAPTER = TypeAdapter(MCMapDownloadClientEvent)
MCMAP_GEN_PALETTE_EVENT_ADAPTER = TypeAdapter(MCMapGenPaletteEvent)
MCMAP_REPLACE_CHUNKS_EVENT_ADAPTER = TypeAdapter(MCMapReplaceChunksEvent)
MCMAP_REMOVE_CHUNKS_EVENT_ADAPTER = TypeAdapter(MCMapRemoveChunksEvent)
MCMAP_FTB_CLAIMS_EVENT_ADAPTER = TypeAdapter(MCMapFtbClaimsEvent)
MCMAP_PLAYERS_EVENT_ADAPTER = TypeAdapter(MCMapPlayersEvent)
MCMAP_PRUNE_EVENT_ADAPTER = TypeAdapter(MCMapPruneEvent)
