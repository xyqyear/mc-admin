from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..logger import logger
from ..mcmap.events import (
    MCMAP_PLAYERS_EVENT_ADAPTER,
    MCMapDimensionEntry,
    MCMapErrorEvent,
    MCMapPlayerRecord,
    MCMapPlayersPayload,
    MCMapPlayersResultEvent,
    MCMapProtocolError,
    MCMapSkippedPlayerFile,
)
from ..world.layout import (
    WorldRootPath,
    discover_world_root_paths,
    resolve_dimension_folder,
)
from .models import (
    PlayerLocationDimensionEntry,
    PlayerLocationEntry,
    PlayerLocationPosition,
    PlayerLocationsResponse,
    PlayerLocationSkippedFile,
)
from .runner import extract_players


class PlayerLocationExtractError(Exception):
    pass


def normalize_uuid(value: str) -> Optional[str]:
    uuid = value.replace("-", "").lower()
    if len(uuid) != 32:
        return None
    if any(c not in "0123456789abcdef" for c in uuid):
        return None
    return uuid


async def _run_extract(world_dir: Path, data_path: Path) -> MCMapPlayersPayload:
    try:
        async with extract_players(world_dir, owned_by=data_path) as proc:
            async for event in proc.events(MCMAP_PLAYERS_EVENT_ADAPTER):
                if isinstance(event, MCMapPlayersResultEvent):
                    await proc.terminate()
                    return event.data
                if isinstance(event, MCMapErrorEvent):
                    raise PlayerLocationExtractError(
                        event.message or "mcmap extract-players failed"
                    )
    except MCMapProtocolError as e:
        raise PlayerLocationExtractError(str(e)) from e
    raise PlayerLocationExtractError(
        "mcmap extract-players produced no terminal event"
    )


def _resolve_dimensions(
    raw_dims: List[MCMapDimensionEntry],
    world_root: WorldRootPath,
    data_path: Path,
) -> Tuple[List[PlayerLocationDimensionEntry], Dict[str, Optional[str]]]:
    entries: List[PlayerLocationDimensionEntry] = []
    relpath_by_dim_id: Dict[str, Optional[str]] = {}
    for raw in raw_dims:
        resolved = resolve_dimension_folder(
            data_path,
            world_root,
            raw.folder,
            exists_on_disk=raw.exists,
        )
        entries.append(
            PlayerLocationDimensionEntry(
                dimension_id=raw.id,
                folder=raw.folder,
                region_dir_relpath=resolved.region_dir_relpath,
                exists_on_disk=resolved.exists_on_disk,
            )
        )
        relpath_by_dim_id[raw.id] = resolved.region_dir_relpath
    return entries, relpath_by_dim_id


def _build_player_entry(
    raw: MCMapPlayerRecord,
    relpath_by_dim_id: Dict[str, Optional[str]],
) -> PlayerLocationEntry:
    pos = PlayerLocationPosition(
        x=raw.pos.x,
        y=raw.pos.y,
        z=raw.pos.z,
    )
    uuid = normalize_uuid(raw.id) if raw.id_kind == "uuid" else None
    return PlayerLocationEntry(
        id=raw.id,
        id_kind=raw.id_kind,
        uuid=uuid,
        source=raw.source,
        storage=raw.storage,
        data_version=raw.data_version,
        dimension_id=raw.dim,
        region_dir_relpath=relpath_by_dim_id.get(raw.dim),
        pos=pos,
    )


def _build_skipped(raw: MCMapSkippedPlayerFile) -> PlayerLocationSkippedFile:
    return PlayerLocationSkippedFile(
        source=raw.source,
        storage=raw.storage,
        reason=raw.reason,
        message=raw.message,
    )


def _shape_response(
    data: MCMapPlayersPayload,
    world_root: WorldRootPath,
    data_path: Path,
) -> PlayerLocationsResponse:
    dimensions, relpath_by_dim_id = _resolve_dimensions(
        data.dimensions,
        world_root,
        data_path,
    )
    players = [_build_player_entry(raw, relpath_by_dim_id) for raw in data.players]
    skipped = [_build_skipped(raw) for raw in data.skipped]
    players.sort(key=lambda p: (p.region_dir_relpath or "", p.id.lower(), p.source))
    return PlayerLocationsResponse(
        dimensions=dimensions,
        players=players,
        skipped=skipped,
    )


async def extract_player_locations_for_server(
    data_path: Path, world_root: Optional[WorldRootPath] = None
) -> PlayerLocationsResponse:
    if world_root is None:
        roots = await discover_world_root_paths(data_path)
        world_root = roots[0] if roots else None
    if world_root is None:
        return PlayerLocationsResponse()
    try:
        data = await _run_extract(world_root.path, data_path)
    except PlayerLocationExtractError:
        logger.exception(
            "player-locations: mcmap extract failed for world=%s", world_root.path
        )
        raise
    return _shape_response(data, world_root, data_path)
