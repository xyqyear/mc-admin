from collections.abc import AsyncGenerator
from contextlib import aclosing
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import desc, func, select

from app.auth.schemas import UserPublic
from app.servers.models import Server, ServerStatus
from app.world.api_models import (
    CreateSnapshotResponse,
    DimensionInfoResponse,
    DimensionLabelsResponse,
    ListEligibleSnapshotsResponse,
    ListRestorationsResponse,
    ManualSnapshotRequest,
    PreviewRequest,
    RestorationResponse,
    RestoreRequest,
    WorldLayoutResponse,
    WorldRootResponse,
)
from app.world.models import Restoration, RestorationType
from app.world.schemas import RestorationSelection

from ... import world as world_subsystem
from ...db.database import get_async_session
from ...dependencies import get_current_user
from ...dynamic_config import get_config
from ...errors import log_safe_error, public_error_message
from ...ftb_claims import (
    ClaimsResponse,
    FtbExtractError,
    extract_claims_for_server,
)
from ...logger import get_logger
from ...minecraft import MCServerStatus, get_docker_mc_manager
from ...player_locations import (
    PlayerLocationExtractError,
    PlayerLocationsResponse,
    extract_player_locations_for_server,
)
from ...self_check.constants import WORLD_RESTORED_TRIGGER, WORLD_ROLLED_BACK_TRIGGER
from ...self_check.events import schedule_self_check_event
from ...snapshots import get_snapshot_service
from ...utils.sse import sse_encode, sse_response
from ...world import (
    SelectionResolutionError,
    ServerNotStoppedError,
    WorldLayoutDiscoveryError,
    WorldRoot,
    discover_world_root_paths,
    discover_world_roots,
)
from ...world.preview import PreviewDiskGuardError, PreviewSessionNotFoundError
from ...world.restoration_store import restoration_binding_issue
from .admission import admit_server_write

router = APIRouter(
    prefix="/servers",
    tags=["world-restore"],
    dependencies=[Depends(admit_server_write)],
)


# --- Helpers ---------------------------------------------------------------


def _get_orchestrator():
    orch = world_subsystem.get_world_restore_orchestrator()
    if not orch:
        raise HTTPException(
            status_code=503,
            detail=(
                "World restore is unavailable: restic is not configured "
                "(check restic settings in config.toml)."
            ),
        )
    return orch


async def _ensure_server_exists(server_id: str) -> None:
    instance = get_docker_mc_manager().get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")


async def _server_is_running(server_id: str) -> bool:
    instance = get_docker_mc_manager().get_instance(server_id)
    status = await instance.get_status()
    return status in (
        MCServerStatus.RUNNING,
        MCServerStatus.STARTING,
        MCServerStatus.HEALTHY,
    )


def _holder_dict(holder) -> dict:
    return {
        "kind": holder.kind.value,
        "started_at": holder.started_at.isoformat(),
        "user_id": holder.user_id,
        "description": holder.description,
        "restoration_id": holder.restoration_id,
    }


# --- Response models -------------------------------------------------------


async def _existing_snapshot_ids() -> set[str] | None:
    # None when restic is unconfigured — existence checks are then skipped.
    snapshot_service = get_snapshot_service()
    if not snapshot_service:
        return None
    snapshots = await snapshot_service.list_snapshots()
    return {s.id for s in snapshots}


def _restoration_to_response(
    row: Restoration, existing_ids: set[str] | None, generation: int | None
) -> RestorationResponse:
    def _exists(snap_id: str | None) -> bool:
        if snap_id is None:
            return False
        if existing_ids is None:
            return True
        return snap_id in existing_ids

    return RestorationResponse(
        id=row.id,
        server_id=row.server_id,
        server_generation=row.server_generation,
        binding_issue=restoration_binding_issue(row, generation),
        type=row.type,
        source_snapshot_id=row.source_snapshot_id,
        safety_snapshot_id=row.safety_snapshot_id,
        source_snapshot_exists=_exists(row.source_snapshot_id),
        safety_snapshot_exists=_exists(row.safety_snapshot_id),
        selection=RestorationSelection.model_validate_json(row.selection_json),
        is_rollback=row.is_rollback,
        initiated_by_user_id=row.initiated_by_user_id,
        started_at=row.started_at,
        finished_at=row.finished_at,
        status=row.status,
        error_message=row.error_message,
    )


def _world_root_to_response(root: WorldRoot) -> WorldRootResponse:
    return WorldRootResponse(
        name=root.name,
        path=str(root.path),
        dimensions=[
            DimensionInfoResponse(
                region_dir=str(d.region_dir),
                entities_dir=str(d.entities_dir) if d.entities_dir else None,
                poi_dir=str(d.poi_dir) if d.poi_dir else None,
            )
            for d in root.dimensions
        ],
    )


async def _get_world_roots(data_path: Path) -> list[WorldRoot]:
    try:
        return await discover_world_roots(data_path)
    except WorldLayoutDiscoveryError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# --- Layout ----------------------------------------------------------------


@router.get("/{server_id}/world-restore/layout", response_model=WorldLayoutResponse)
async def get_layout(
    server_id: str, _: UserPublic = Depends(get_current_user)
) -> WorldLayoutResponse:
    await _ensure_server_exists(server_id)
    instance = get_docker_mc_manager().get_instance(server_id)
    data_path = instance.get_data_path()

    roots = await _get_world_roots(data_path)
    return WorldLayoutResponse(world_roots=[_world_root_to_response(r) for r in roots])


@router.get(
    "/{server_id}/world-restore/dimension-labels",
    response_model=DimensionLabelsResponse,
)
async def get_dimension_labels(
    server_id: str, _: UserPublic = Depends(get_current_user)
) -> DimensionLabelsResponse:
    await _ensure_server_exists(server_id)
    return DimensionLabelsResponse(dimension_labels=dict(get_config().world.dimension_labels))


# --- FTB claims ------------------------------------------------------------


@router.get(
    "/{server_id}/claims",
    response_model=ClaimsResponse,
)
@router.get(
    "/{server_id}/world-restore/claims",
    response_model=ClaimsResponse,
)
async def get_ftb_claims(
    server_id: str,
    _: UserPublic = Depends(get_current_user),
) -> ClaimsResponse:
    await _ensure_server_exists(server_id)
    instance = get_docker_mc_manager().get_instance(server_id)
    data_path = instance.get_data_path()
    roots = await discover_world_root_paths(data_path)
    if not roots:
        return ClaimsResponse(available=False)
    try:
        return await extract_claims_for_server(
            data_path,
            world_root=roots[0],
        )
    except FtbExtractError as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Player locations ------------------------------------------------------


@router.get(
    "/{server_id}/player-locations",
    response_model=PlayerLocationsResponse,
)
@router.get(
    "/{server_id}/world-restore/player-locations",
    response_model=PlayerLocationsResponse,
)
async def get_player_locations(
    server_id: str,
    _: UserPublic = Depends(get_current_user),
) -> PlayerLocationsResponse:
    await _ensure_server_exists(server_id)
    instance = get_docker_mc_manager().get_instance(server_id)
    data_path = instance.get_data_path()
    roots = await discover_world_root_paths(data_path)
    if not roots:
        return PlayerLocationsResponse()
    try:
        return await extract_player_locations_for_server(
            data_path,
            world_root=roots[0],
        )
    except PlayerLocationExtractError as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Eligible snapshots ----------------------------------------------------


@router.post(
    "/{server_id}/world-restore/eligible-snapshots",
    response_model=ListEligibleSnapshotsResponse,
)
async def eligible_snapshots(
    server_id: str,
    selection: RestorationSelection,
    _: UserPublic = Depends(get_current_user),
) -> ListEligibleSnapshotsResponse:
    await _ensure_server_exists(server_id)
    orch = _get_orchestrator()
    try:
        snapshots = await orch.list_eligible_snapshots(server_id, selection)
    except SelectionResolutionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ListEligibleSnapshotsResponse(snapshots=snapshots)


# --- Snapshot creation -----------------------------------------------------


@router.post(
    "/{server_id}/world-restore/snapshots",
    response_model=CreateSnapshotResponse,
)
async def create_snapshot(
    server_id: str,
    request: ManualSnapshotRequest,
    user: UserPublic = Depends(get_current_user),
) -> CreateSnapshotResponse:
    logger = get_logger()
    await _ensure_server_exists(server_id)
    orch = _get_orchestrator()
    if world_subsystem.get_server_operation_lock().is_locked(server_id):
        holder = world_subsystem.get_server_operation_lock().get_holder(server_id)
        raise HTTPException(
            status_code=423,
            detail={
                "reason": "locked",
                "holder": _holder_dict(holder) if holder else None,
            },
        )
    selection = RestorationSelection(
        type=RestorationType(request.type),
        region_dir_relpath=request.region_dir_relpath,
    )
    try:
        snapshot = await orch.create_snapshot(server_id, selection, user.id)
    except SelectionResolutionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    logger.info(
        "world snapshot created: %s for server=%s (type=%s)",
        snapshot.short_id,
        server_id,
        selection.type.value,
    )
    return CreateSnapshotResponse(
        message=f"Snapshot {snapshot.short_id} created",
        snapshot=snapshot,
    )


# --- Preview ---------------------------------------------------------------


@router.post("/{server_id}/world-restore/preview")
async def begin_preview(
    server_id: str,
    body: PreviewRequest,
    _: UserPublic = Depends(get_current_user),
) -> StreamingResponse:
    await _ensure_server_exists(server_id)
    orch = _get_orchestrator()

    async def event_gen() -> AsyncGenerator[bytes]:
        try:
            async with aclosing(orch.begin_preview(
                server_id=server_id,
                source_snapshot_id=body.source_snapshot_id,
                selection=body.selection,
            )) as events:
                async for event in events:
                    yield sse_encode(event.model_dump(exclude_none=True))
        except PreviewDiskGuardError as e:
            yield sse_encode(
                {
                    "event_type": "error",
                    "message": str(e),
                    "free": e.free,
                    "required": e.required,
                }
            )
        except SelectionResolutionError as e:
            yield sse_encode({"event_type": "error", "message": str(e)})
        except Exception as e:  # noqa: BLE001 - preview failures must exclude raw adapter diagnostics
            log_safe_error(e, "World preview stream failed")
            yield sse_encode({"event_type": "error", "message": public_error_message(e)})

    return sse_response(event_gen())


@router.post(
    "/{server_id}/world-restore/preview/{session_id}/heartbeat",
    status_code=204,
)
async def heartbeat_preview(
    server_id: str,
    session_id: str,
    _: UserPublic = Depends(get_current_user),
) -> None:
    await _ensure_server_exists(server_id)
    orch = _get_orchestrator()
    try:
        await orch.require_preview_owner(server_id, session_id)
        orch.heartbeat_preview(session_id)
    except PreviewSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Preview session not found")


@router.delete(
    "/{server_id}/world-restore/preview/{session_id}",
    status_code=204,
)
async def end_preview(
    server_id: str,
    session_id: str,
    _: UserPublic = Depends(get_current_user),
) -> None:
    await _ensure_server_exists(server_id)
    orch = _get_orchestrator()
    try:
        await orch.require_preview_owner(server_id, session_id, missing_ok=True)
    except PreviewSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Preview session not found")
    await orch.end_preview(session_id)


@router.get("/{server_id}/world-restore/preview/{session_id}/tile/{rx}/{rz}.png")
async def get_preview_tile(
    server_id: str,
    session_id: str,
    rx: int,
    rz: int,
    _: UserPublic = Depends(get_current_user),
) -> Response:
    await _ensure_server_exists(server_id)
    orch = _get_orchestrator()

    # Heartbeat before awaiting render so coalesced bursts keep the session alive.
    try:
        await orch.require_preview_owner(server_id, session_id)
        orch.heartbeat_preview(session_id)
    except PreviewSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Preview session not found")

    try:
        tile = await orch.read_preview_tile(session_id, rx, rz)
    except PreviewSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Preview session not found")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Preview tile not available")
    except TimeoutError:
        raise HTTPException(status_code=503, detail="Render timed out, retry")
    return Response(
        tile,
        media_type="image/png",
        headers={
            "Cache-Control": "private, max-age=60",
        },
    )


# --- Restoration -----------------------------------------------------------


@router.post("/{server_id}/world-restore/restore")
async def begin_restore(
    server_id: str,
    body: RestoreRequest,
    user: UserPublic = Depends(get_current_user),
) -> StreamingResponse:
    await _ensure_server_exists(server_id)
    orch = _get_orchestrator()

    if await _server_is_running(server_id):
        raise HTTPException(
            status_code=409,
            detail={
                "reason": "server_running",
                "message": "Stop the server before starting a restore",
            },
        )
    if world_subsystem.get_server_operation_lock().is_locked(server_id):
        holder = world_subsystem.get_server_operation_lock().get_holder(server_id)
        raise HTTPException(
            status_code=423,
            detail={
                "reason": "locked",
                "holder": _holder_dict(holder) if holder else None,
            },
        )

    async def event_gen() -> AsyncGenerator[bytes]:
        try:
            terminal = None
            async with aclosing(orch.begin_restore(
                server_id=server_id,
                source_snapshot_id=body.source_snapshot_id,
                selection=body.selection,
                user_id=user.id,
            )) as events:
                async for event in events:
                    if event.event_type in {"complete", "error"}:
                        terminal = event
                    else:
                        yield sse_encode(event.model_dump(exclude_none=True))
            if terminal is not None:
                if terminal.event_type == "complete":
                    schedule_self_check_event(WORLD_RESTORED_TRIGGER, user.id)
                yield sse_encode(terminal.model_dump(exclude_none=True))
        except ServerNotStoppedError as e:
            yield sse_encode({"event_type": "error", "message": str(e)})
        except SelectionResolutionError as e:
            yield sse_encode({"event_type": "error", "message": str(e)})
        except Exception as e:  # noqa: BLE001 - retain the finite stream's safe error event
            log_safe_error(e, "World restore stream failed")
            yield sse_encode({"event_type": "error", "message": public_error_message(e)})

    return sse_response(event_gen())


# --- Restoration history ---------------------------------------------------


@router.get(
    "/{server_id}/world-restore/restorations",
    response_model=ListRestorationsResponse,
)
async def list_restorations(
    server_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: UserPublic = Depends(get_current_user),
) -> ListRestorationsResponse:
    await _ensure_server_exists(server_id)

    async with get_async_session() as session:
        generation = await session.scalar(select(Server.id).where(
            Server.server_id == server_id, Server.status == ServerStatus.ACTIVE,
        ))
        total = (
            await session.execute(
                select(func.count(Restoration.id)).where(
                    Restoration.server_id == server_id
                )
            )
        ).scalar_one()
        rows = (
            (
                await session.execute(
                    select(Restoration)
                    .where(Restoration.server_id == server_id)
                    .order_by(desc(Restoration.started_at))
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
    existing_ids = await _existing_snapshot_ids()
    return ListRestorationsResponse(
        restorations=[_restoration_to_response(r, existing_ids, generation) for r in rows],
        total=int(total),
    )


@router.get(
    "/{server_id}/world-restore/restorations/{restoration_id}",
    response_model=RestorationResponse,
)
async def get_restoration(
    server_id: str,
    restoration_id: str,
    _: UserPublic = Depends(get_current_user),
) -> RestorationResponse:
    await _ensure_server_exists(server_id)
    async with get_async_session() as session:
        generation = await session.scalar(select(Server.id).where(
            Server.server_id == server_id, Server.status == ServerStatus.ACTIVE,
        ))
        row = (
            await session.execute(
                select(Restoration).where(Restoration.id == restoration_id)
            )
        ).scalar_one_or_none()
    if row is None or row.server_id != server_id:
        raise HTTPException(status_code=404, detail="Restoration not found")
    existing_ids = await _existing_snapshot_ids()
    return _restoration_to_response(row, existing_ids, generation)


@router.post("/{server_id}/world-restore/restorations/{restoration_id}/rollback")
async def rollback_restoration(
    server_id: str,
    restoration_id: str,
    user: UserPublic = Depends(get_current_user),
) -> StreamingResponse:
    await _ensure_server_exists(server_id)
    orch = _get_orchestrator()

    # Validate up-front so 404/400 surfaces before the SSE handshake.
    async with get_async_session() as session:
        row = (
            await session.execute(
                select(Restoration).where(Restoration.id == restoration_id)
            )
        ).scalar_one_or_none()
    if row is None or row.server_id != server_id:
        raise HTTPException(status_code=404, detail="Restoration not found")
    await orch.require_rollback_owner(row)
    if not row.safety_snapshot_id:
        raise HTTPException(
            status_code=400,
            detail="Restoration has no safety snapshot to roll back to",
        )
    existing_ids = await _existing_snapshot_ids()
    if existing_ids is not None and row.safety_snapshot_id not in existing_ids:
        raise HTTPException(
            status_code=400,
            detail="Safety snapshot has been deleted; rollback is no longer possible",
        )

    if await _server_is_running(server_id):
        raise HTTPException(
            status_code=409,
            detail={
                "reason": "server_running",
                "message": "Stop the server before rolling back a restoration",
            },
        )
    if world_subsystem.get_server_operation_lock().is_locked(server_id):
        holder = world_subsystem.get_server_operation_lock().get_holder(server_id)
        raise HTTPException(
            status_code=423,
            detail={
                "reason": "locked",
                "holder": _holder_dict(holder) if holder else None,
            },
        )

    async def event_gen() -> AsyncGenerator[bytes]:
        try:
            terminal = None
            async with aclosing(orch.rollback(restoration_id, user.id)) as events:
                async for event in events:
                    if event.event_type in {"complete", "error"}:
                        terminal = event
                    else:
                        yield sse_encode(event.model_dump(exclude_none=True))
            if terminal is not None:
                if terminal.event_type == "complete":
                    schedule_self_check_event(WORLD_ROLLED_BACK_TRIGGER, user.id)
                yield sse_encode(terminal.model_dump(exclude_none=True))
        except Exception as e:  # noqa: BLE001 - retain the finite stream's safe error event
            log_safe_error(e, "World rollback stream failed")
            yield sse_encode({"event_type": "error", "message": public_error_message(e)})

    return sse_response(event_gen())


# --- Crash recovery --------------------------------------------------------
