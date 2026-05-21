from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..logger import logger
from ..world.layout import DimensionInfo, WorldRoot, discover_world_roots
from .cluster import build_clusters
from .models import (
    ClaimDimensionEntry,
    ClaimMember,
    ClaimsResponse,
    ClusterEntry,
    DetectedFormat,
    TeamEntry,
)
from .runner import extract_ftb_claims

NO_FTB_DATA_MESSAGE_SUBSTRING = "could not detect FTB claim format"

_VALID_FORMATS = {"snbt", "per_team_nbt", "universe_dat", "latmod_json"}


class NoFtbDataError(Exception):
    pass


class FtbExtractError(Exception):
    pass


async def _run_extract(world_dir: Path, data_path: Path) -> dict:
    async with extract_ftb_claims(world_dir, owned_by=data_path) as proc:
        terminal: Optional[dict] = None
        async for event in proc:
            event_type = event.get("type")
            if event_type in ("result", "error"):
                terminal = event
                break
        await proc.terminate()
    if terminal is None:
        stderr = ""
        raise FtbExtractError(
            f"mcmap extract-ftb-claims produced no terminal event ({stderr!r})"
        )
    if terminal.get("type") == "error":
        message = str(terminal.get("message", ""))
        if NO_FTB_DATA_MESSAGE_SUBSTRING in message:
            raise NoFtbDataError(message)
        raise FtbExtractError(message or "mcmap extract-ftb-claims failed")
    data = terminal.get("data")
    if not isinstance(data, dict):
        raise FtbExtractError("mcmap result event is missing 'data' payload")
    return data


def _resolve_dimensions(
    raw_dims: List[dict],
    world_root: WorldRoot,
    data_path: Path,
) -> Tuple[List[ClaimDimensionEntry], Dict[str, Optional[str]]]:
    layout_by_region_dir: Dict[Path, DimensionInfo] = {
        d.region_dir: d for d in world_root.dimensions
    }

    entries: List[ClaimDimensionEntry] = []
    relpath_by_ftb_id: Dict[str, Optional[str]] = {}
    for raw in raw_dims:
        ftb_id = str(raw.get("id", ""))
        folder = str(raw.get("folder", ""))
        exists_on_disk = bool(raw.get("exists", False))
        if folder == "." or folder == "":
            candidate = world_root.path / "region"
        else:
            candidate = world_root.path / folder / "region"
        match = layout_by_region_dir.get(candidate)
        if match is not None:
            try:
                rel = match.region_dir.relative_to(data_path).as_posix()
            except ValueError:
                rel = None
            entries.append(
                ClaimDimensionEntry(
                    ftb_id=ftb_id,
                    region_dir_relpath=rel,
                    exists_on_disk=True,
                )
            )
            relpath_by_ftb_id[ftb_id] = rel
        else:
            entries.append(
                ClaimDimensionEntry(
                    ftb_id=ftb_id,
                    region_dir_relpath=None,
                    exists_on_disk=exists_on_disk,
                )
            )
            relpath_by_ftb_id[ftb_id] = None
    return entries, relpath_by_ftb_id


def _display_name(team: dict) -> str:
    # pre-1.13 FTB returns name=null; fall back to owner → first member → id prefix.
    name = team.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    owner = team.get("owner") or {}
    if isinstance(owner, dict):
        oname = owner.get("name")
        if isinstance(oname, str) and oname.strip():
            return oname.strip()
    for member in team.get("members") or []:
        if not isinstance(member, dict):
            continue
        mname = member.get("name")
        if isinstance(mname, str) and mname.strip():
            return mname.strip()
    tid = str(team.get("id") or "")
    return tid[:8] if tid else "(unknown)"


def _parse_member(raw: dict) -> ClaimMember:
    return ClaimMember(
        uuid=raw.get("uuid") if isinstance(raw.get("uuid"), str) else None,
        name=raw.get("name") if isinstance(raw.get("name"), str) else None,
        rank=raw.get("rank") if isinstance(raw.get("rank"), str) else None,
    )


def _coerce_team_type(raw: object) -> str:
    if raw in ("player", "party", "server"):
        return raw  # type: ignore[return-value]
    return "unknown"


def _build_team_entry(
    raw_team: dict,
    relpath_by_ftb_id: Dict[str, Optional[str]],
) -> TeamEntry:
    team_id = str(raw_team.get("id") or "")
    members_raw = raw_team.get("members") or []
    owner_raw = raw_team.get("owner")
    claims_raw = raw_team.get("claims") or []

    by_dim_claims: Dict[str, List[Tuple[int, int]]] = {}
    by_dim_force: Dict[str, List[Tuple[int, int]]] = {}
    for claim in claims_raw:
        if not isinstance(claim, dict):
            continue
        dim = str(claim.get("dim") or "")
        try:
            cx = int(claim.get("cx"))  # type: ignore[arg-type]
            cz = int(claim.get("cz"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        by_dim_claims.setdefault(dim, []).append((cx, cz))
        if bool(claim.get("force_loaded")):
            by_dim_force.setdefault(dim, []).append((cx, cz))

    clusters: List[ClusterEntry] = []
    for dim_id, chunks in by_dim_claims.items():
        rel = relpath_by_ftb_id.get(dim_id)
        clusters.extend(
            build_clusters(
                team_id=team_id,
                region_dir_relpath=rel,
                claims=chunks,
                force_loaded=by_dim_force.get(dim_id, []),
            )
        )

    total_chunks = sum(len(c.chunks) for c in clusters)
    members = [_parse_member(m) for m in members_raw if isinstance(m, dict)]
    owner = _parse_member(owner_raw) if isinstance(owner_raw, dict) else None
    return TeamEntry(
        id=team_id,
        display_name=_display_name(raw_team),
        type=_coerce_team_type(raw_team.get("type")),  # type: ignore[arg-type]
        members=members,
        owner=owner,
        total_chunks=total_chunks,
        clusters=clusters,
    )


def _coerce_detected_format(raw: object) -> Optional[DetectedFormat]:
    if isinstance(raw, str) and raw in _VALID_FORMATS:
        return raw  # type: ignore[return-value]
    return None


def _shape_response(
    data: dict,
    world_root: WorldRoot,
    data_path: Path,
) -> ClaimsResponse:
    raw_dims = data.get("dimensions") or []
    raw_teams = data.get("teams") or []
    dimensions, relpath_by_ftb_id = _resolve_dimensions(
        raw_dims if isinstance(raw_dims, list) else [],
        world_root,
        data_path,
    )
    teams = [
        _build_team_entry(t, relpath_by_ftb_id)
        for t in raw_teams
        if isinstance(t, dict)
    ]
    teams.sort(key=lambda t: (t.display_name.lower(), t.id))
    return ClaimsResponse(
        available=True,
        detected_format=_coerce_detected_format(data.get("detected_format")),
        dimensions=dimensions,
        teams=teams,
    )


async def extract_claims_for_server(
    data_path: Path, roots: Optional[List[WorldRoot]] = None
) -> ClaimsResponse:
    if roots is None:
        roots = await discover_world_roots(data_path)
    if not roots:
        return ClaimsResponse(available=False)
    primary = roots[0]
    try:
        data = await _run_extract(primary.path, data_path)
    except NoFtbDataError:
        return ClaimsResponse(available=False)
    except FtbExtractError:
        logger.exception(
            "ftb-claims: mcmap extract failed for world=%s", primary.path
        )
        raise
    return _shape_response(data, primary, data_path)
