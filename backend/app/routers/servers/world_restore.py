"""Per-server world-restore endpoints.

This router exposes the ``WorldRestoreOrchestrator`` over HTTP/SSE. It is
mounted under ``/api/servers/{server_id}/world-restore/`` (the prefix used by
sibling per-server routers — note that ``/servers`` is the router prefix and
``{server_id}`` is part of each endpoint path). All endpoints require an
authenticated user (``get_current_user`` — ADMIN+).

SSE streams use ``StreamingResponse`` framed as ``data: <json>\\n\\n`` blocks
(consistent with ``app/routers/servers/map.py``). The frontend consumes them
via a manual fetch + ``\\n\\n`` parser.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import desc, func, select

from ... import world as world_subsystem
from ...db.database import get_async_session
from ...dependencies import get_current_user
from ...logger import logger
from ...minecraft import MCServerStatus, docker_mc_manager
from ...models import (
    Restoration,
    RestorationSelection,
    RestorationStatus,
    RestorationType,
    UserPublic,
)
from ...snapshots import ResticSnapshot, ResticSnapshotWithSummary, restic_manager
from ...world import (
    SelectionResolutionError,
    ServerNotStoppedError,
    WorldRoot,
)
from ...world.preview import PreviewDiskGuardError, PreviewSessionNotFoundError

router = APIRouter(
    prefix="/servers",
    tags=["world-restore"],
)


# --- Helpers ---------------------------------------------------------------


def _get_orchestrator():
    orch = world_subsystem.world_restore_orchestrator
    if orch is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "World restore is unavailable: restic is not configured "
                "(check restic settings in config.toml)."
            ),
        )
    return orch


async def _ensure_server_exists(server_id: str) -> None:
    instance = docker_mc_manager.get_instance(server_id)
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")


async def _server_is_running(server_id: str) -> bool:
    instance = docker_mc_manager.get_instance(server_id)
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


def _sse(event_obj: dict) -> bytes:
    return f"data: {json.dumps(event_obj, separators=(',', ':'))}\n\n".encode()


# --- Response models -------------------------------------------------------


class DimensionInfoResponse(BaseModel):
    label: str
    region_dir: str
    entities_dir: Optional[str] = None
    poi_dir: Optional[str] = None


class WorldRootResponse(BaseModel):
    name: str
    path: str
    dimensions: List[DimensionInfoResponse]


class WorldLayoutResponse(BaseModel):
    world_roots: List[WorldRootResponse]


class ListEligibleSnapshotsResponse(BaseModel):
    snapshots: List[ResticSnapshot]


class CreateSnapshotResponse(BaseModel):
    message: str
    snapshot: ResticSnapshotWithSummary


class ManualSnapshotRequest(BaseModel):
    """Request body for the manual snapshot endpoint.

    Manual snapshots only ever cover a whole dimension or the whole server.
    Region- and chunk-scope snapshots exist only as the safety snapshots taken
    automatically inside ``begin_restore`` before a rollback — they have no
    user-facing entry point. ``Literal`` here makes Pydantic reject the
    narrower scopes at parse time (HTTP 422) instead of further down the call
    stack.
    """

    type: Literal["world", "dimension"]
    region_dir_relpath: Optional[str] = None


class PreviewRequest(BaseModel):
    source_snapshot_id: str
    selection: RestorationSelection


class RestoreRequest(BaseModel):
    source_snapshot_id: str
    selection: RestorationSelection


class RestorationResponse(BaseModel):
    id: str
    server_id: str
    type: RestorationType
    source_snapshot_id: str
    safety_snapshot_id: Optional[str]
    # Whether each referenced snapshot still exists in the restic repo. Filled
    # at request time by listing restic snapshots once and intersecting IDs.
    # Restorations whose safety snapshot is gone can no longer be rolled back.
    source_snapshot_exists: bool
    safety_snapshot_exists: bool
    selection: RestorationSelection
    is_rollback: bool
    initiated_by_user_id: Optional[int]
    started_at: datetime
    finished_at: Optional[datetime]
    status: RestorationStatus
    error_message: Optional[str]


class ListRestorationsResponse(BaseModel):
    restorations: List[RestorationResponse]
    total: int


async def _existing_snapshot_ids() -> Optional[set[str]]:
    """Snapshot IDs currently present in the restic repo, or ``None`` if
    restic isn't configured (in which case existence checks are skipped and
    historical rows are reported as still existing — they predate the deletion
    we'd be flagging anyway)."""
    if restic_manager is None:
        return None
    snapshots = await restic_manager.list_snapshots()
    return {s.id for s in snapshots}


def _restoration_to_response(
    row: Restoration, existing_ids: Optional[set[str]]
) -> RestorationResponse:
    def _exists(snap_id: Optional[str]) -> bool:
        if snap_id is None:
            return False
        if existing_ids is None:
            return True
        return snap_id in existing_ids

    return RestorationResponse(
        id=row.id,
        server_id=row.server_id,
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
                label=d.label,
                region_dir=str(d.region_dir),
                entities_dir=str(d.entities_dir) if d.entities_dir else None,
                poi_dir=str(d.poi_dir) if d.poi_dir else None,
            )
            for d in root.dimensions
        ],
    )


# --- Layout ----------------------------------------------------------------


@router.get("/{server_id}/world-restore/layout", response_model=WorldLayoutResponse)
async def get_layout(
    server_id: str, _: UserPublic = Depends(get_current_user)
) -> WorldLayoutResponse:
    """Return discovered world roots and their dimensions for the server."""
    await _ensure_server_exists(server_id)
    instance = docker_mc_manager.get_instance(server_id)
    data_path = instance.get_data_path()

    from ...world.layout import discover_world_roots

    roots = await discover_world_roots(data_path)
    return WorldLayoutResponse(
        world_roots=[_world_root_to_response(r) for r in roots]
    )


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
    """Return snapshots that cover every path the selection resolves to."""
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
    """Create a manual snapshot at world or dimension scope.

    Region- and chunk-scope snapshots are intentionally not exposed here:
    they are only created automatically as safety snapshots before a
    rollback. Pydantic rejects those scopes at parse time via the
    ``ManualSnapshotRequest.type`` literal.

    Acquires the server's BACKUP lock for the duration. Returns 423 if the
    server is currently locked by another operation.
    """
    await _ensure_server_exists(server_id)
    orch = _get_orchestrator()
    if world_subsystem.server_operation_lock.is_locked(server_id):
        holder = world_subsystem.server_operation_lock.get_holder(server_id)
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
    """Stream preview-staging events as Server-Sent Events.

    Tears down any prior preview session for this server before starting.
    """
    await _ensure_server_exists(server_id)
    orch = _get_orchestrator()

    async def event_gen() -> AsyncGenerator[bytes, None]:
        try:
            async for event in orch.begin_preview(
                server_id=server_id,
                source_snapshot_id=body.source_snapshot_id,
                selection=body.selection,
            ):
                yield _sse(event.model_dump(exclude_none=True))
        except PreviewDiskGuardError as e:
            yield _sse(
                {
                    "event_type": "error",
                    "message": str(e),
                    "free": e.free,
                    "required": e.required,
                }
            )
        except SelectionResolutionError as e:
            yield _sse({"event_type": "error", "message": str(e)})
        except Exception as e:
            logger.exception("preview stream failed for server=%s", server_id)
            yield _sse({"event_type": "error", "message": str(e)})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/{server_id}/world-restore/preview/{session_id}/heartbeat",
    status_code=204,
)
async def heartbeat_preview(
    server_id: str,
    session_id: str,
    _: UserPublic = Depends(get_current_user),
) -> None:
    """Refresh the session's last-seen timestamp."""
    await _ensure_server_exists(server_id)
    orch = _get_orchestrator()
    try:
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
    """Tear down a preview session. Idempotent."""
    await _ensure_server_exists(server_id)
    orch = _get_orchestrator()
    await orch.end_preview(session_id)


@router.get(
    "/{server_id}/world-restore/preview/{session_id}/tile/{rx}/{rz}.png"
)
async def get_preview_tile(
    server_id: str,
    session_id: str,
    rx: int,
    rz: int,
    _: UserPublic = Depends(get_current_user),
) -> FileResponse:
    """Serve a preview tile, lazily rendering on first miss.

    Mirrors the live-map tile endpoint: if the PNG is already on disk, returns
    it directly; otherwise enqueues a render on the session's per-dimension
    ``ServerRenderQueue`` and awaits completion (with the same
    ``request_timeout_seconds`` budget). 503 on render timeout, 404 if the
    session is gone or the requested region wasn't staged.
    """
    await _ensure_server_exists(server_id)
    orch = _get_orchestrator()

    # Heartbeat *before* awaiting render so the session doesn't TTL-expire
    # mid-render, and so duplicate-tile-request bursts keep the session alive
    # even when most of them coalesce onto the same in-flight Future.
    try:
        orch.heartbeat_preview(session_id)
    except PreviewSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Preview session not found")

    try:
        tile = await orch.request_preview_tile(session_id, rx, rz)
    except PreviewSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Preview session not found")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Preview tile not available")
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Render timed out, retry")
    return FileResponse(
        str(tile),
        media_type="image/png",
        headers={
            "Cache-Control": "private, max-age=60",
            "Vary": "Authorization",
        },
    )


# --- Restoration -----------------------------------------------------------


@router.post("/{server_id}/world-restore/restore")
async def begin_restore(
    server_id: str,
    body: RestoreRequest,
    user: UserPublic = Depends(get_current_user),
) -> StreamingResponse:
    """Stream the restore flow as SSE.

    Returns 409 if the server is running, 423 if the server is currently
    locked by another operation. Both checks happen *before* the SSE handshake
    so the frontend sees a normal HTTP error response.
    """
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
    if world_subsystem.server_operation_lock.is_locked(server_id):
        holder = world_subsystem.server_operation_lock.get_holder(server_id)
        raise HTTPException(
            status_code=423,
            detail={
                "reason": "locked",
                "holder": _holder_dict(holder) if holder else None,
            },
        )

    async def event_gen() -> AsyncGenerator[bytes, None]:
        try:
            async for event in orch.begin_restore(
                server_id=server_id,
                source_snapshot_id=body.source_snapshot_id,
                selection=body.selection,
                user_id=user.id,
            ):
                yield _sse(event.model_dump(exclude_none=True))
        except ServerNotStoppedError as e:
            yield _sse({"event_type": "error", "message": str(e)})
        except SelectionResolutionError as e:
            yield _sse({"event_type": "error", "message": str(e)})
        except Exception as e:
            logger.exception("restore stream failed for server=%s", server_id)
            yield _sse({"event_type": "error", "message": str(e)})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- Restoration history ---------------------------------------------------


@router.get(
    "/{server_id}/world-restore/restorations",
    response_model=ListRestorationsResponse,
)
async def list_restorations(
    server_id: str,
    limit: int = 50,
    offset: int = 0,
    _: UserPublic = Depends(get_current_user),
) -> ListRestorationsResponse:
    """Paginated history for this server, newest-first."""
    await _ensure_server_exists(server_id)
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be in [1, 200]")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")

    async with get_async_session() as session:
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
        restorations=[_restoration_to_response(r, existing_ids) for r in rows],
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
        row = (
            await session.execute(
                select(Restoration).where(Restoration.id == restoration_id)
            )
        ).scalar_one_or_none()
    if row is None or row.server_id != server_id:
        raise HTTPException(status_code=404, detail="Restoration not found")
    existing_ids = await _existing_snapshot_ids()
    return _restoration_to_response(row, existing_ids)


@router.post("/{server_id}/world-restore/restorations/{restoration_id}/rollback")
async def rollback_restoration(
    server_id: str,
    restoration_id: str,
    user: UserPublic = Depends(get_current_user),
) -> StreamingResponse:
    """Roll back a prior restoration by re-running with its safety snapshot."""
    await _ensure_server_exists(server_id)
    orch = _get_orchestrator()

    # Validate the row up-front so we can surface a 404/400 *before* the SSE
    # handshake — the orchestrator's ``rollback`` would otherwise raise inside
    # the generator after the response headers were sent.
    async with get_async_session() as session:
        row = (
            await session.execute(
                select(Restoration).where(Restoration.id == restoration_id)
            )
        ).scalar_one_or_none()
    if row is None or row.server_id != server_id:
        raise HTTPException(status_code=404, detail="Restoration not found")
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
    if world_subsystem.server_operation_lock.is_locked(server_id):
        holder = world_subsystem.server_operation_lock.get_holder(server_id)
        raise HTTPException(
            status_code=423,
            detail={
                "reason": "locked",
                "holder": _holder_dict(holder) if holder else None,
            },
        )

    async def event_gen() -> AsyncGenerator[bytes, None]:
        try:
            async for event in orch.rollback(restoration_id, user.id):
                yield _sse(event.model_dump(exclude_none=True))
        except Exception as e:
            logger.exception(
                "rollback stream failed for server=%s restoration=%s",
                server_id,
                restoration_id,
            )
            yield _sse({"event_type": "error", "message": str(e)})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- Crash recovery --------------------------------------------------------


async def mark_running_restorations_interrupted() -> int:
    """Flip any ``RUNNING`` restoration rows to ``INTERRUPTED`` on startup.

    Returns the number of rows updated. Factored out for testability.
    """
    from datetime import timezone as _tz

    from sqlalchemy import update

    async with get_async_session() as session:
        result = await session.execute(
            update(Restoration)
            .where(Restoration.status == RestorationStatus.RUNNING)
            .values(
                status=RestorationStatus.INTERRUPTED,
                error_message="server restarted before completion",
                finished_at=datetime.now(_tz.utc),
            )
        )
        await session.commit()
    count = result.rowcount or 0
    if count:
        logger.info(
            "world restore: flipped %d running restoration(s) to interrupted on startup",
            count,
        )
    return int(count)


# Re-exported for ``app/main.py`` lifespan.
__all__ = ["router", "mark_running_restorations_interrupted"]
