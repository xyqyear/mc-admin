from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..logger import logger
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


async def _run_extract(world_dir: Path, data_path: Path) -> dict:
    async with extract_players(world_dir, owned_by=data_path) as proc:
        terminal: Optional[dict] = None
        async for event in proc:
            event_type = event.get("type")
            if event_type in ("result", "error"):
                terminal = event
                break
        await proc.terminate()
    if terminal is None:
        raise PlayerLocationExtractError(
            "mcmap extract-players produced no terminal event"
        )
    if terminal.get("type") == "error":
        message = str(terminal.get("message", ""))
        raise PlayerLocationExtractError(message or "mcmap extract-players failed")
    data = terminal.get("data")
    if not isinstance(data, dict):
        raise PlayerLocationExtractError("mcmap result event is missing 'data' payload")
    return data


def _resolve_dimensions(
    raw_dims: List[dict],
    world_root: WorldRootPath,
    data_path: Path,
) -> Tuple[List[PlayerLocationDimensionEntry], Dict[str, Optional[str]]]:
    entries: List[PlayerLocationDimensionEntry] = []
    relpath_by_dim_id: Dict[str, Optional[str]] = {}
    for raw in raw_dims:
        dim_id = str(raw.get("id", ""))
        folder = str(raw.get("folder", ""))
        exists_on_disk = bool(raw.get("exists", False))
        resolved = resolve_dimension_folder(
            data_path,
            world_root,
            folder,
            exists_on_disk=exists_on_disk,
        )
        entries.append(
            PlayerLocationDimensionEntry(
                dimension_id=dim_id,
                folder=folder,
                region_dir_relpath=resolved.region_dir_relpath,
                exists_on_disk=resolved.exists_on_disk,
            )
        )
        relpath_by_dim_id[dim_id] = resolved.region_dir_relpath
    return entries, relpath_by_dim_id


def _build_player_entry(
    raw: dict,
    relpath_by_dim_id: Dict[str, Optional[str]],
) -> Optional[PlayerLocationEntry]:
    raw_pos = raw.get("pos")
    if not isinstance(raw_pos, dict):
        return None
    try:
        pos = PlayerLocationPosition(
            x=float(raw_pos.get("x")),
            y=float(raw_pos.get("y")),
            z=float(raw_pos.get("z")),
        )
    except (TypeError, ValueError):
        return None

    player_id = str(raw.get("id") or "")
    id_kind = raw.get("id_kind")
    if id_kind not in ("uuid", "name"):
        return None
    storage = raw.get("storage")
    if storage not in ("playerdata", "players_data", "legacy_players"):
        return None
    dim_id = str(raw.get("dim") or "")
    uuid = normalize_uuid(player_id) if id_kind == "uuid" else None
    data_version = raw.get("data_version")
    return PlayerLocationEntry(
        id=player_id,
        id_kind=id_kind,
        uuid=uuid,
        source=str(raw.get("source") or ""),
        storage=storage,
        data_version=data_version if isinstance(data_version, int) else None,
        dimension_id=dim_id,
        region_dir_relpath=relpath_by_dim_id.get(dim_id),
        pos=pos,
    )


def _build_skipped(raw: dict) -> Optional[PlayerLocationSkippedFile]:
    reason = raw.get("reason")
    storage = raw.get("storage")
    if reason not in (
        "parse_error",
        "missing_pos",
        "invalid_pos",
        "missing_dimension",
        "invalid_dimension",
    ):
        return None
    if storage not in ("playerdata", "players_data", "legacy_players"):
        return None
    message = raw.get("message")
    return PlayerLocationSkippedFile(
        source=str(raw.get("source") or ""),
        storage=storage,
        reason=reason,
        message=message if isinstance(message, str) else None,
    )


def _shape_response(
    data: dict,
    world_root: WorldRootPath,
    data_path: Path,
) -> PlayerLocationsResponse:
    raw_dims = data.get("dimensions") or []
    raw_players = data.get("players") or []
    raw_skipped = data.get("skipped") or []
    dimensions, relpath_by_dim_id = _resolve_dimensions(
        raw_dims if isinstance(raw_dims, list) else [],
        world_root,
        data_path,
    )
    players = [
        entry
        for raw in raw_players
        if isinstance(raw, dict)
        for entry in [_build_player_entry(raw, relpath_by_dim_id)]
        if entry is not None
    ]
    skipped = [
        entry
        for raw in raw_skipped
        if isinstance(raw, dict)
        for entry in [_build_skipped(raw)]
        if entry is not None
    ]
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
