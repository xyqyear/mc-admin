"""Typed JSON events emitted by the mcmap CLI."""

from typing import Annotated, Any, Literal, Optional, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class MCMapProtocolError(Exception):
    pass


class MCMapEventModel(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)


class MCMapProgressEvent(MCMapEventModel):
    type: Literal["progress"]
    phase: str
    elapsed_ms: Optional[int] = None
    count: Optional[int] = None
    bytes: Optional[int] = None
    total: Optional[int] = None
    index: Optional[int] = None
    path: Optional[str] = None


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
    output: Optional[str] = None
    error: Optional[str] = None
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
    failed: Optional[int] = None


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


MCMapDetectedFtbFormat: TypeAlias = Literal[
    "snbt",
    "per_team_nbt",
    "universe_dat",
    "latmod_json",
]

MCMapFtbTeamType: TypeAlias = Literal["player", "party", "server", "unknown"]
MCMapPlayerIdKind: TypeAlias = Literal["uuid", "name"]
MCMapPlayerStorageKind: TypeAlias = Literal[
    "playerdata", "players_data", "legacy_players"
]
MCMapPlayerSkipReason: TypeAlias = Literal[
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
    uuid: Optional[str] = None
    name: Optional[str] = None
    rank: Optional[str] = None


class MCMapFtbClaim(MCMapEventModel):
    dim: str
    cx: int
    cz: int
    force_loaded: bool


class MCMapFtbTeam(MCMapEventModel):
    id: str
    name: Optional[str] = None
    type: MCMapFtbTeamType
    owner: Optional[MCMapFtbMember] = None
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
    output: Optional[str] = None
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
    data_version: Optional[int] = None
    dim: str
    pos: MCMapPlayerPosition


class MCMapSkippedPlayerFile(MCMapEventModel):
    source: str
    storage: MCMapPlayerStorageKind
    reason: MCMapPlayerSkipReason
    message: Optional[str] = None


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
    output: Optional[str] = None
    data: MCMapPlayersPayload


MCMapGenericEvent: TypeAlias = Annotated[
    MCMapProgressEvent
    | MCMapRenderRegionEvent
    | MCMapGenericResultEvent
    | MCMapErrorEvent
    | MCMapChunkReplaceEvent
    | MCMapChunkRemoveEvent,
    Field(discriminator="type"),
]
MCMapRenderEvent: TypeAlias = Annotated[
    MCMapProgressEvent
    | MCMapRenderRegionEvent
    | MCMapRenderResultEvent
    | MCMapErrorEvent,
    Field(discriminator="type"),
]
MCMapDownloadClientEvent: TypeAlias = Annotated[
    MCMapProgressEvent | MCMapDownloadClientResultEvent | MCMapErrorEvent,
    Field(discriminator="type"),
]
MCMapGenPaletteEvent: TypeAlias = Annotated[
    MCMapProgressEvent | MCMapGenPaletteResultEvent | MCMapErrorEvent,
    Field(discriminator="type"),
]
MCMapReplaceChunksEvent: TypeAlias = Annotated[
    MCMapChunkReplaceEvent | MCMapReplaceChunksResultEvent | MCMapErrorEvent,
    Field(discriminator="type"),
]
MCMapRemoveChunksEvent: TypeAlias = Annotated[
    MCMapChunkRemoveEvent | MCMapRemoveChunksResultEvent | MCMapErrorEvent,
    Field(discriminator="type"),
]
MCMapFtbClaimsEvent: TypeAlias = Annotated[
    MCMapFtbClaimsResultEvent | MCMapErrorEvent,
    Field(discriminator="type"),
]
MCMapPlayersEvent: TypeAlias = Annotated[
    MCMapPlayersResultEvent | MCMapErrorEvent,
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
