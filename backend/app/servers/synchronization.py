import asyncio
from collections.abc import AsyncGenerator

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..background_tasks import TaskProgress, TaskType, get_task_manager
from ..background_tasks.api_models import TaskAccepted
from ..config import get_settings
from ..db.database import get_async_session
from ..dns import get_dns_manager
from ..errors import log_safe_error, public_error_message
from ..minecraft import get_docker_mc_manager
from ..operations.context import current_execution, record_phase
from ..operations.journal_types import ResourceReference
from ..runtime_resources import current_runtime
from .api_models import SyncRequest
from .crud import get_active_servers
from .lifecycle import (
    CreateServerResult,
    RemoveServerResult,
    SyncDryRunEntry,
    SyncEntryError,
    SyncResult,
    adopt_server_partial,
    deactivate_server_partial,
    preview_deactivation,
    validate_adoption,
)
from .references import ServerRef, resolve_server_ref


def get_sync_lock() -> asyncio.Lock:
    return current_runtime().resource('server_sync_lock')


async def synchronize(db: AsyncSession, body: SyncRequest, references: tuple[ServerRef, ...]) -> SyncResult:
    if get_sync_lock().locked():
        raise HTTPException(
            status_code=409, detail="另一个同步任务正在进行中"
        )

    async with get_sync_lock():
        fs_set = set(await get_docker_mc_manager().get_all_server_names())
        active = await get_active_servers(db)
        active_set = {s.server_id for s in active}
        if {(s.server_id, s.id) for s in active} != {(ref.server_id, ref.generation) for ref in references}:
            raise HTTPException(status_code=409, detail="服务器登记状态已变化，请重新同步")

        fs_only = sorted(fs_set - active_set)
        db_only = sorted(active_set - fs_set)

        if not body.force and len(fs_set) == 0 and len(db_only) > 0:
            raise HTTPException(
                status_code=409,
                detail={"code": "sync_empty_directory", "message": "拒绝在服务器目录为空时停用所有数据库记录；如确认请使用 force=true"},
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
            except Exception as e:  # noqa: BLE001 - retain per-server outcomes without exposing adapter errors
                log_safe_error(e, "同步服务器校验失败")
                errors.append(
                    SyncEntryError(
                        server_id=sid, stage="validate", error=public_error_message(e)
                    )
                )

        for sid in db_only:
            try:
                jobs, sessions = await preview_deactivation(db, sid)
            except Exception as e:  # noqa: BLE001 - retain per-server outcomes without exposing adapter errors
                log_safe_error(e, "同步服务器停用预览失败")
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
            except Exception as e:  # noqa: BLE001 - retain per-server outcomes without exposing adapter errors
                log_safe_error(e, "同步服务器接管失败")
                errors.append(
                    SyncEntryError(
                        server_id=sid, stage="adopt", error=public_error_message(e)
                    )
                )

        for sid in db_only:
            try:
                removed.append(await deactivate_server_partial(db, sid))
            except Exception as e:  # noqa: BLE001 - retain per-server outcomes without exposing adapter errors
                log_safe_error(e, "同步服务器停用失败")
                errors.append(
                    SyncEntryError(
                        server_id=sid, stage="deactivate", error=public_error_message(e)
                    )
                )

            finally:
                if execution := current_execution():
                    execution.servers = tuple(ref for ref in execution.servers if ref.server_id != sid)

        try:
            await get_dns_manager().update(db)
        except Exception as e:  # noqa: BLE001 - retain per-server outcomes without exposing adapter errors
            log_safe_error(e, "同步服务器后的 DNS 更新失败")

        return SyncResult(
            applied=True,
            adopted=adopted,
            removed=removed,
            preview=preview,
            errors=errors,
        )


async def sync_task(body: SyncRequest, references: tuple[ServerRef, ...]) -> AsyncGenerator[TaskProgress]:
    yield TaskProgress(message="正在扫描并核对服务器登记状态")
    await record_phase("synchronizing_servers", changed=not body.dry_run)
    async with get_async_session() as session:
        result = await synchronize(session, body, references)
    yield TaskProgress(progress=100, message="同步完成，部分服务器需要检查" if result.errors else "服务器同步完成",
                       result=result.model_dump(mode="json"))


async def submit_sync(body: SyncRequest, actor_id: int) -> TaskAccepted:
    async with get_async_session() as session:
        references = tuple([await resolve_server_ref(session, server.server_id,
                            servers_root=get_settings().server_path, require_exists=False)
                            for server in await get_active_servers(session)])
    resources = (ResourceReference("files"), *(ResourceReference("server", ref.server_id, ref.generation) for ref in references))
    submitted = await get_task_manager().submit_durable(
        TaskType.SERVER_SYNC, "预览服务器同步" if body.dry_run else "同步服务器",
        sync_task(body.model_copy(deep=True), references), server_refs=references,
        resources=resources, require_existing_targets=False, cancellable=False,
        actor_id=actor_id, exclusive_key="server-sync",
    )
    return TaskAccepted(task_id=submitted.task_id)
