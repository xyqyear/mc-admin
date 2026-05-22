from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..logger import logger
from ..mcmap.events import (
    MCMAP_FTB_CLAIMS_EVENT_ADAPTER,
    MCMapDimensionEntry,
    MCMapErrorEvent,
    MCMapFtbClaimsPayload,
    MCMapFtbClaimsResultEvent,
    MCMapFtbMember,
    MCMapFtbTeam,
    MCMapProtocolError,
)
from ..world.layout import (
    WorldRootPath,
    discover_world_root_paths,
    resolve_dimension_folder,
)
from .cluster import build_clusters
from .models import (
    ClaimDimensionEntry,
    ClaimMember,
    ClaimsResponse,
    ClusterEntry,
    TeamEntry,
)
from .runner import extract_ftb_claims

NO_FTB_DATA_MESSAGE_SUBSTRING = "could not detect FTB claim format"


class NoFtbDataError(Exception):
    pass


class FtbExtractError(Exception):
    pass


async def _run_extract(world_dir: Path, data_path: Path) -> MCMapFtbClaimsPayload:
    try:
        async with extract_ftb_claims(world_dir, owned_by=data_path) as proc:
            async for event in proc.events(MCMAP_FTB_CLAIMS_EVENT_ADAPTER):
                if isinstance(event, MCMapFtbClaimsResultEvent):
                    await proc.terminate()
                    return event.data
                if isinstance(event, MCMapErrorEvent):
                    if NO_FTB_DATA_MESSAGE_SUBSTRING in event.message:
                        raise NoFtbDataError(event.message)
                    raise FtbExtractError(
                        event.message or "mcmap extract-ftb-claims failed"
                    )
            stderr = await proc.stderr()
    except MCMapProtocolError as e:
        raise FtbExtractError(str(e)) from e
    raise FtbExtractError(
        f"mcmap extract-ftb-claims produced no terminal event ({stderr!r})"
    )


def _resolve_dimensions(
    raw_dims: List[MCMapDimensionEntry],
    world_root: WorldRootPath,
    data_path: Path,
) -> Tuple[List[ClaimDimensionEntry], Dict[str, Optional[str]]]:
    entries: List[ClaimDimensionEntry] = []
    relpath_by_ftb_id: Dict[str, Optional[str]] = {}
    for raw in raw_dims:
        resolved = resolve_dimension_folder(
            data_path,
            world_root,
            raw.folder,
            exists_on_disk=raw.exists,
        )
        entries.append(
            ClaimDimensionEntry(
                ftb_id=raw.id,
                region_dir_relpath=resolved.region_dir_relpath,
                exists_on_disk=resolved.exists_on_disk,
            )
        )
        relpath_by_ftb_id[raw.id] = resolved.region_dir_relpath
    return entries, relpath_by_ftb_id


def _display_name(team: MCMapFtbTeam) -> str:
    # pre-1.13 FTB can return name=null; fall back to owner, member, then id.
    if team.name is not None and team.name.strip():
        return team.name.strip()
    if team.owner is not None and team.owner.name is not None:
        owner_name = team.owner.name.strip()
        if owner_name:
            return owner_name
    for member in team.members:
        if member.name is None:
            continue
        member_name = member.name.strip()
        if member_name:
            return member_name
    return team.id[:8] if team.id else "(unknown)"


def _parse_member(raw: MCMapFtbMember) -> ClaimMember:
    return ClaimMember(
        uuid=raw.uuid,
        name=raw.name,
        rank=raw.rank,
    )


def _build_team_entry(
    raw_team: MCMapFtbTeam,
    relpath_by_ftb_id: Dict[str, Optional[str]],
) -> TeamEntry:
    by_dim_claims: Dict[str, List[Tuple[int, int]]] = {}
    by_dim_force: Dict[str, List[Tuple[int, int]]] = {}
    for claim in raw_team.claims:
        chunk = (claim.cx, claim.cz)
        by_dim_claims.setdefault(claim.dim, []).append(chunk)
        if claim.force_loaded:
            by_dim_force.setdefault(claim.dim, []).append(chunk)

    clusters: List[ClusterEntry] = []
    for dim_id, chunks in by_dim_claims.items():
        rel = relpath_by_ftb_id.get(dim_id)
        clusters.extend(
            build_clusters(
                team_id=raw_team.id,
                region_dir_relpath=rel,
                claims=chunks,
                force_loaded=by_dim_force.get(dim_id, []),
            )
        )

    total_chunks = sum(len(c.chunks) for c in clusters)
    members = [_parse_member(m) for m in raw_team.members]
    owner = _parse_member(raw_team.owner) if raw_team.owner is not None else None
    return TeamEntry(
        id=raw_team.id,
        display_name=_display_name(raw_team),
        type=raw_team.type,
        members=members,
        owner=owner,
        total_chunks=total_chunks,
        clusters=clusters,
    )


def _shape_response(
    data: MCMapFtbClaimsPayload,
    world_root: WorldRootPath,
    data_path: Path,
) -> ClaimsResponse:
    dimensions, relpath_by_ftb_id = _resolve_dimensions(
        data.dimensions,
        world_root,
        data_path,
    )
    teams = [_build_team_entry(t, relpath_by_ftb_id) for t in data.teams]
    teams.sort(key=lambda t: (t.display_name.lower(), t.id))
    return ClaimsResponse(
        available=True,
        detected_format=data.detected_format,
        dimensions=dimensions,
        teams=teams,
    )


async def extract_claims_for_server(
    data_path: Path, world_root: Optional[WorldRootPath] = None
) -> ClaimsResponse:
    if world_root is None:
        roots = await discover_world_root_paths(data_path)
        world_root = roots[0] if roots else None
    if world_root is None:
        return ClaimsResponse(available=False)
    try:
        data = await _run_extract(world_root.path, data_path)
    except NoFtbDataError:
        return ClaimsResponse(available=False)
    except FtbExtractError:
        logger.exception(
            "ftb-claims: mcmap extract failed for world=%s", world_root.path
        )
        raise
    return _shape_response(data, world_root, data_path)
