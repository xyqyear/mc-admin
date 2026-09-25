"""Populate a stopped instance while owning its files and consumed archive."""

from collections.abc import AsyncGenerator
from contextlib import aclosing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from aiofiles import os as aioos
from fastapi import HTTPException

from ..archive.application import archive_claims
from ..background_tasks import TaskProgress
from ..config import get_settings
from ..minecraft import MCInstance, MCServerStatus
from ..operations.context import (
    current_execution,
    record_phase,
    retain_recovery_reference,
)
from ..operations.coordinator import ConflictPolicy, ResourceClaim, ResourceKind
from ..operations.execution import settle_before_release
from ..operations.finalization import finalize
from ..utils import async_fs
from ..utils.decompression import extract_minecraft_server
from ..world.locks import LockHolder, ServerOperationKind, get_server_operation_lock
from .resources import path_claims, require_same_claims

POPULATION_PREFIX = ".mc-admin-populate-"


@dataclass(frozen=True)
class PopulationPlan:
    instance: MCInstance
    archive: Path
    archive_root: Path
    stage: Path
    token: str
    claims: tuple[ResourceClaim, ...]


async def check_population_status(instance: MCInstance) -> None:
    status = await instance.get_status()
    if status == MCServerStatus.REMOVED:
        raise HTTPException(status_code=404, detail=f"服务器 '{instance.get_name()}' 不存在")
    if status not in (MCServerStatus.EXISTS, MCServerStatus.CREATED):
        raise HTTPException(status_code=409, detail=f"服务器 '{instance.get_name()}' 必须处于 'exists' 或 'created' 状态才能覆盖文件 (当前状态: {status})")


async def _claims(instance: MCInstance, archive: Path, stage: Path, archive_root: Path) -> tuple[ResourceClaim, ...]:
    return (
        ResourceClaim(ResourceKind.MAINTENANCE, instance.get_name()),
        *await path_claims(instance.get_project_path(), [instance.get_data_path(), stage], server_id=instance.get_name()),
        *await archive_claims(archive_root, [archive]),
    )


async def prepare_population(instance: MCInstance, archive: Path, *, archive_root: Path | None = None) -> PopulationPlan:
    settings = get_settings()
    token = uuid4().hex
    stage = instance.get_project_path() / f"{POPULATION_PREFIX}{token}.tmp"
    root = archive_root if archive_root is not None else settings.archive_path
    return PopulationPlan(instance, archive, root, stage, token, await _claims(instance, archive, stage, root))


async def populate(plan: PopulationPlan, *, actor_id: int | None = None) -> AsyncGenerator[TaskProgress]:
    instance = plan.instance
    holder = LockHolder(ServerOperationKind.RESTORE, datetime.now(UTC), actor_id, "填充服务器文件")
    async with get_server_operation_lock().lease([instance.get_name()], holder, claims=plan.claims, policy=ConflictPolicy.REJECT), settle_before_release():
        require_same_claims(plan.claims, await _claims(instance, plan.archive, plan.stage, plan.archive_root))
        await check_population_status(instance)
        await retain_recovery_reference("population_stage", plan.token)
        try:
            await finalize(aioos.mkdir(plan.stage))
            await record_phase("populating_files", changed=True)
            async with aclosing(extract_minecraft_server(str(plan.archive), str(instance.get_data_path()), temporary_dir=plan.stage)) as events:
                async for event in events:
                    yield event
        finally:
            async def cleanup() -> None:
                execution = current_execution()
                if execution is not None:
                    record = await execution.journal.get(execution.operation_id)
                    if record is None or record.processes or not record.ownership_known:
                        return
                try:
                    await async_fs.rmtree(plan.stage)
                except FileNotFoundError:
                    pass
                if execution is not None:
                    await execution.journal.resolve_reference(execution.operation_id, "population_stage", plan.token)
            await finalize(cleanup())
