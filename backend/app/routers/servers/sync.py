"""POST /api/servers/sync: reconcile filesystem ↔ ACTIVE Server rows."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_db
from ...dependencies import RequireRole
from ...dns import simple_dns_manager
from ...logger import logger
from ...minecraft import docker_mc_manager
from ...models import UserPublic, UserRole
from ...servers import (
    CreateServerResult,
    RemoveServerResult,
    SyncDryRunEntry,
    SyncEntryError,
    SyncResult,
    adopt_server_partial,
    deactivate_server_partial,
    get_active_servers,
    preview_deactivation,
    validate_adoption,
)

router = APIRouter(
    prefix="/servers",
    tags=["server-sync"],
)


_sync_lock = asyncio.Lock()


class SyncRequest(BaseModel):
    dry_run: bool = False
    # force=true bypasses the empty-filesystem safety guard that would
    # otherwise refuse to deactivate every row when the mount has failed.
    force: bool = False


@router.post("/sync", response_model=SyncResult)
async def sync_servers(
    body: SyncRequest = SyncRequest(),
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(RequireRole(UserRole.OWNER)),
) -> SyncResult:
    # Reject concurrent calls with 409 rather than queueing on the lock —
    # a fast 409 beats an indefinite hang on an HTTP worker.
    if _sync_lock.locked():
        raise HTTPException(
            status_code=409, detail="另一个同步任务正在进行中"
        )

    async with _sync_lock:
        fs_set = set(await docker_mc_manager.get_all_server_names())
        active = await get_active_servers(db)
        active_set = {s.server_id for s in active}

        fs_only = sorted(fs_set - active_set)
        db_only = sorted(active_set - fs_set)

        if not body.force and len(fs_set) == 0 and len(db_only) > 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    "拒绝在服务器目录为空时停用所有数据库记录；"
                    "如确认请使用 force=true"
                ),
            )

        admit: list[tuple[str, int, int]] = []
        errors: list[SyncEntryError] = []
        preview: list[SyncDryRunEntry] = []

        for sid in fs_only:
            try:
                game_port, rcon_port = await validate_adoption(db, sid)
                admit.append((sid, game_port, rcon_port))
                preview.append(
                    SyncDryRunEntry(
                        server_id=sid,
                        action="adopt",
                        game_port=game_port,
                        rcon_port=rcon_port,
                    )
                )
            except Exception as e:
                errors.append(
                    SyncEntryError(
                        server_id=sid, stage="validate", error=str(e)
                    )
                )

        for sid in db_only:
            try:
                jobs, sessions = await preview_deactivation(db, sid)
            except Exception:
                jobs, sessions = 0, 0
            preview.append(
                SyncDryRunEntry(
                    server_id=sid,
                    action="deactivate",
                    restart_cronjob_count=jobs,
                    open_session_count=sessions,
                )
            )

        if body.dry_run:
            return SyncResult(
                applied=False, preview=preview, errors=errors
            )

        adopted: list[CreateServerResult] = []
        removed: list[RemoveServerResult] = []

        for sid, game_port, rcon_port in admit:
            try:
                adopted.append(
                    await adopt_server_partial(
                        db, sid, game_port=game_port, rcon_port=rcon_port
                    )
                )
            except Exception as e:
                errors.append(
                    SyncEntryError(
                        server_id=sid, stage="adopt", error=str(e)
                    )
                )

        for sid in db_only:
            try:
                removed.append(await deactivate_server_partial(db, sid))
            except Exception as e:
                errors.append(
                    SyncEntryError(
                        server_id=sid, stage="deactivate", error=str(e)
                    )
                )

        try:
            await simple_dns_manager.update(db)
        except Exception as e:
            logger.warning(f"sync: dns update failed: {e}")

        return SyncResult(
            applied=True,
            adopted=adopted,
            removed=removed,
            preview=preview,
            errors=errors,
        )
