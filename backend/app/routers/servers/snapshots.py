"""Snapshot management endpoints for Minecraft servers using restic"""

from typing import Optional

from fastapi import APIRouter, Depends

from ...dependencies import get_current_user
from ...models import UserPublic
from ..snapshots import (
    CreateSnapshotRequest,
    CreateSnapshotResponse,
    ListSnapshotsResponse,
    RestorePreviewRequest,
    RestorePreviewResponse,
    RestoreRequest,
    create_global_snapshot,
    list_global_snapshots,
    preview_global_restore,
    restore_global_snapshot,
)

router = APIRouter(
    prefix="/servers",
    tags=["snapshots"],
)


# Specific server snapshot endpoints
@router.post("/{server_id}/snapshots", response_model=CreateSnapshotResponse)
async def create_server_snapshot(
    server_id: str,
    path: Optional[str] = None,
    _: UserPublic = Depends(get_current_user),
):
    """Create snapshot for specific server"""
    request = CreateSnapshotRequest(server_id=server_id, path=path)
    return await create_global_snapshot(request, _)


@router.get("/{server_id}/snapshots", response_model=ListSnapshotsResponse)
async def list_server_snapshots(
    server_id: str,
    path: Optional[str] = None,
    _: UserPublic = Depends(get_current_user),
):
    """List snapshots for specific server"""
    return await list_global_snapshots(server_id=server_id, path=path, _=_)


@router.post(
    "/{server_id}/snapshots/restore/preview", response_model=RestorePreviewResponse
)
async def preview_server_restore(
    server_id: str,
    snapshot_id: str,
    path: Optional[str] = None,
    _: UserPublic = Depends(get_current_user),
):
    """Preview restore for specific server"""
    request = RestorePreviewRequest(
        snapshot_id=snapshot_id, server_id=server_id, path=path
    )
    return await preview_global_restore(request, _)


@router.post("/{server_id}/snapshots/restore")
async def restore_server_snapshot(
    server_id: str,
    snapshot_id: str,
    path: Optional[str] = None,
    _: UserPublic = Depends(get_current_user),
):
    """Restore snapshot for specific server"""
    request = RestoreRequest(snapshot_id=snapshot_id, server_id=server_id, path=path)
    return await restore_global_snapshot(request, _)
