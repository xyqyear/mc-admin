"""Compatibility execution scopes for tasks, requests and scheduled commands."""

import asyncio
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import TYPE_CHECKING, Literal

from ..config import get_settings
from ..db.database import get_async_session
from ..errors import PublicOperationError, public_error_code
from ..operation_admission import get_server_write_admission
from ..runtime_resources import current_runtime
from ..servers.references import resolve_server_ref
from .context import OperationExecution, bind_execution, current_execution
from .coordinator import ResourceClaim
from .finalization import finalize
from .journal import InvalidOperationTransition, OperationJournal
from .journal_types import (
    TERMINAL_STATES,
    OperationRecord,
    OperationSpec,
    OperationState,
    ResourceReference,
)
from .processes import confirm_stopped
from .resources import journal_resources, require_contained_resources

if TYPE_CHECKING:
    from ..runtime import Runtime


async def settle_execution(execution: OperationExecution, state: OperationState) -> None:
    from .recovery import RecoveryService

    if execution.settled:
        return
    record = await execution.journal.get(execution.operation_id)
    if record is None:
        raise RuntimeError("操作记录不存在")
    stopped = record.writers_stopped if record.state in TERMINAL_STATES else not record.processes and record.ownership_known
    if record.state in TERMINAL_STATES and record.state not in {state, execution.outcome}:
        raise InvalidOperationTransition()
    if record.state in TERMINAL_STATES:
        state = record.state
    if not stopped:
        state = OperationState.INTERRUPTED
        if any(resource.kind == "cache" for resource in record.resources):
            execution.cache_degraded = True
        for resource in record.resources:
            if resource.kind == "global" or (resource.kind == "files" and resource.server_id is None):
                get_server_write_admission().block_global("全局操作的写入尚未确认结束，请检查操作历史")
            elif resource.kind == "archive":
                get_server_write_admission().block_archive(resource.path, "压缩包操作的写入尚未确认结束，请检查操作历史")
            elif resource.kind != "cache" and resource.server_id:
                get_server_write_admission().block(resource.server_id, "中断操作的写入尚未确认结束，请检查操作历史")
    reconcile = stopped and state in {OperationState.FAILED, OperationState.CANCELLED, OperationState.INTERRUPTED} and RecoveryService.configuration_changed(record)
    if record.state not in TERMINAL_STATES:
        record = await execution.journal.finish(
            execution.operation_id, state, writers_stopped=stopped,
            failure_code=execution.failure_code,
            cache_degraded=execution.cache_degraded,
            blocked_reason="configuration_reconciliation_required" if reconcile else None,
        )
    execution.outcome = record.state
    if reconcile:
        runtime = current_runtime()
        recovery = runtime.resources.get("operation_recovery")
        if recovery is None:
            recovery = RecoveryService(
                execution.journal, probe=confirm_runtime_writers_stopped,
                servers_root=runtime.settings.server_path,
                archive_root=runtime.settings.archive_path,
            )
            runtime.resources["operation_recovery"] = recovery
        await recovery.reconcile_terminal(record.operation_id)
        await recovery.apply_blocks(get_server_write_admission())
    if not stopped:
        recovery = current_runtime().resources.get("operation_recovery")
        if recovery is not None:
            await recovery.apply_blocks(get_server_write_admission())
        execution.settled = True
        raise PublicOperationError("操作写入尚未确认结束，请检查操作历史并完成恢复验证")
    execution.settled = True


@asynccontextmanager
async def settle_before_release() -> AsyncGenerator[None]:
    """Install any recovery block while the failed operation still owns its lease."""
    try:
        yield
    except BaseException as failure:
        execution = current_execution()
        if execution is not None:
            if isinstance(failure, Exception):
                execution.failure_code = public_error_code(failure)
            async def settle_failure(error: BaseException) -> None:
                record = await execution.journal.get(execution.operation_id)
                cancelled = isinstance(error, (asyncio.CancelledError, GeneratorExit))
                state = (OperationState.INTERRUPTED if record is not None and record.origin == "request" else OperationState.CANCELLED) if cancelled else OperationState.FAILED
                await settle_execution(execution, execution.outcome or state)
            try:
                await finalize(settle_failure(failure))
            except BaseException as cleanup_failure:
                raise failure from cleanup_failure
        raise
    else:
        execution = current_execution()
        if execution is not None and not execution.settled:
            async def settle_outcome() -> None:
                record = await execution.journal.get(execution.operation_id)
                if execution.outcome is not None or (record is not None and (record.processes or not record.ownership_known)):
                    await settle_execution(execution, execution.outcome or OperationState.SUCCEEDED)
            await finalize(settle_outcome())


@asynccontextmanager
async def operation_scope(
    kind: str,
    server_ids: Sequence[str],
    *,
    actor_id: int | None = None,
    origin: Literal["task", "cron", "request", "system"] = "request",
    legacy_id: str | None = None,
    name: str = "",
    require_exists: bool = True,
    configuration_version: str | None = None,
    claims: Sequence[ResourceClaim] | None = None,
) -> AsyncGenerator[OperationExecution | None]:
    settings = get_settings()
    journal = current_runtime().journal
    if journal is None:
        yield None
        return
    parent = current_execution()
    resource_kind = {"world_restore": "world", "snapshot_restore": "files"}.get(kind, "server")
    if parent is not None:
        if not set(server_ids).issubset({server.server_id for server in parent.servers}):
            raise RuntimeError("子操作不能扩大已声明的服务器范围")
        if claims is not None:
            resources = journal_resources([server for server in parent.servers if server.server_id in server_ids], claims, default_kind=resource_kind)
            record = await journal.get(parent.operation_id)
            if record is None:
                raise RuntimeError("操作记录不存在")
            require_contained_resources(record.resources, resources)
        yield parent
        return
    async with get_async_session() as db:
        servers = tuple([
            await resolve_server_ref(db, server_id, servers_root=settings.server_path, require_exists=require_exists)
            for server_id in sorted(set(server_ids))
        ])
    resources = journal_resources(servers, claims, default_kind=resource_kind) if claims is not None else tuple(ResourceReference(resource_kind, ref.server_id, ref.generation) for ref in servers)
    record = await journal.accept(OperationSpec(
        kind=kind, resources=resources or (ResourceReference("global"),), actor_id=actor_id,
        origin=origin, legacy_id=legacy_id, name=name or kind,
        configuration_version=configuration_version,
    ))
    execution = OperationExecution(journal, record.operation_id, servers)
    with bind_execution(execution):
        state = OperationState.FAILED
        try:
            await journal.start(record.operation_id)
            yield execution
            state = execution.outcome or OperationState.SUCCEEDED
        except (asyncio.CancelledError, GeneratorExit):
            state = OperationState.INTERRUPTED if origin == "request" else OperationState.CANCELLED
            raise
        except Exception as error:
            execution.failure_code = public_error_code(error)
            raise
        finally:
            await finalize(settle_execution(execution, state))


async def confirm_runtime_writers_stopped(record: OperationRecord) -> bool:
    settings = get_settings()
    if not await confirm_stopped(replace(record, ownership_known=True)):
        return False
    if record.ownership_known:
        return True
    from ..minecraft import get_docker_mc_manager

    async with get_async_session() as db:
        for resource in record.resources:
            if resource.server_id is None:
                return False
            ref = await resolve_server_ref(db, resource.server_id, servers_root=settings.server_path)
            if ref.generation != resource.generation:
                return False
            if await get_docker_mc_manager().get_instance(ref.server_id).created():
                return False
    return True


async def recover_runtime(runtime: "Runtime") -> None:
    from ..background_tasks import get_task_manager
    from ..cron.crud import interrupt_running_executions
    from ..world.recovery import mark_running_restorations_interrupted
    from .recovery import RecoveryService

    journal = OperationJournal(runtime.database.session_factory)
    runtime.journal = journal
    runtime.resources["operation_journal"] = journal
    recovery = RecoveryService(
        journal, probe=confirm_runtime_writers_stopped, servers_root=runtime.settings.server_path,
        archive_root=runtime.settings.archive_path,
    )
    runtime.resources["operation_recovery"] = recovery
    await recovery.recover()
    await recovery.apply_blocks(get_server_write_admission())
    await mark_running_restorations_interrupted()
    async with runtime.database.session_factory() as session:
        await interrupt_running_executions(session)
    get_task_manager().journal = journal
    offset = 0
    while records := await journal.list(limit=1000, offset=offset, origin="task"):
        get_task_manager().restore_history(records)
        offset += len(records)
