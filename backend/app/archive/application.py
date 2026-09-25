"""Archive mutations and atomic publication with owned source and output scope."""

import re
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import aclosing
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from aiofiles import os as aioos

from ..background_tasks import TaskProgress
from ..config import get_settings
from ..files import base
from ..files.paths import resolve_file_path, validate_file_name
from ..files.resources import path_claims, require_same_claims
from ..files.types import CreateFileRequest, RenameFileRequest
from ..minecraft import MCInstance
from ..operations.context import (
    current_execution,
    record_phase,
    retain_recovery_reference,
)
from ..operations.coordinator import (
    ConflictPolicy,
    ResourceClaim,
    ResourceKind,
    get_operation_coordinator,
)
from ..operations.execution import operation_scope, settle_before_release
from ..operations.finalization import finalize
from ..utils import async_fs
from ..utils.compression import create_server_archive_stream, generate_archive_filename

STAGE_PREFIX = ".mc-admin-archive-"


def is_archive_stage(name: str) -> bool:
    return re.fullmatch(r"\.mc-admin-archive-[a-f0-9]{32}\.tmp", name) is not None


async def archive_claims(base_path: Path, paths: Sequence[Path]) -> tuple[ResourceClaim, ...]:
    return await path_claims(base_path, paths, kind=ResourceKind.ARCHIVE)


async def mutate_archive[T](
    base_path: Path, paths: Sequence[Path], action: Callable[[], Awaitable[T]], *,
    kind: str = "archive_write", actor_id: int | None = None,
    policy: ConflictPolicy = ConflictPolicy.REJECT,
) -> T:
    claims = await archive_claims(base_path, paths)
    async with (
        operation_scope(kind, [], actor_id=actor_id, claims=claims),
        get_operation_coordinator().acquire(claims, policy=policy),
        settle_before_release(),
    ):
        require_same_claims(claims, await archive_claims(base_path, paths))
        await record_phase("writing_archive", changed=True)
        return await finalize(action())


class ArchiveApplication:
    def __init__(self, root: Path, actor_id: int | None = None) -> None:
        self.root = root
        self.actor_id = actor_id

    async def create(self, request: CreateFileRequest) -> str:
        validate_file_name(request.name)
        target = await resolve_file_path(self.root, str(Path(request.path) / request.name))
        return await mutate_archive(self.root, [target], lambda: base.create_file_or_directory(self.root, request), actor_id=self.actor_id)

    async def delete(self, path: str) -> str:
        target = await resolve_file_path(self.root, path)
        return await mutate_archive(self.root, [target], lambda: base.delete_file_or_directory(self.root, path), actor_id=self.actor_id)

    async def rename(self, request: RenameFileRequest) -> str:
        validate_file_name(request.new_name)
        source = await resolve_file_path(self.root, request.old_path)
        target = await resolve_file_path(self.root, str((source.parent / request.new_name).relative_to(self.root)))
        return await mutate_archive(self.root, [source, target], lambda: base.rename_file_or_directory(self.root, request), actor_id=self.actor_id)


@dataclass(frozen=True)
class CompressionPlan:
    instance: MCInstance
    relative_path: str | None
    source: Path
    output: Path
    stage: Path
    token: str
    claims: tuple[ResourceClaim, ...]


async def prepare_compression(instance: MCInstance, relative_path: str | None) -> CompressionPlan:
    settings = get_settings()
    source = instance.get_project_path() if relative_path is None else await resolve_file_path(instance.get_data_path(), relative_path)
    archive_root = await async_fs.resolve(settings.archive_path)
    token = uuid4().hex
    stage = archive_root / f"{STAGE_PREFIX}{token}.tmp"
    output = archive_root / generate_archive_filename(instance.get_name(), relative_path)
    claims = (*await path_claims(instance.get_project_path(), [source], server_id=instance.get_name()), *await archive_claims(archive_root, [output, stage]))
    return CompressionPlan(instance, relative_path, source, output, stage, token, claims)


async def compress(plan: CompressionPlan) -> AsyncGenerator[TaskProgress]:
    async with get_operation_coordinator().acquire(plan.claims, policy=ConflictPolicy.REJECT), settle_before_release():
        actual = (*await path_claims(plan.instance.get_project_path(), [plan.source], server_id=plan.instance.get_name()), *await archive_claims(plan.output.parent, [plan.output, plan.stage]))
        require_same_claims(plan.claims, actual)
        await retain_recovery_reference("archive_stage", plan.token)
        await record_phase("compressing_archive")
        try:
            async with aclosing(create_server_archive_stream(plan.instance, plan.relative_path, output_path=plan.stage)) as events:
                async for event in events:
                    if event.result is None:
                        yield event
            await record_phase("publishing_archive", changed=True)
            await finalize(aioos.replace(plan.stage, plan.output))
            size = (await aioos.stat(plan.output)).st_size
        finally:
            async def cleanup() -> None:
                execution = current_execution()
                if execution is not None:
                    record = await execution.journal.get(execution.operation_id)
                    if record is None or record.processes or not record.ownership_known:
                        return
                try:
                    await aioos.unlink(plan.stage)
                except FileNotFoundError:
                    pass
                if execution is not None:
                    await execution.journal.resolve_reference(execution.operation_id, "archive_stage", plan.token)
            await finalize(cleanup())
        yield TaskProgress(progress=100, message="Compression complete", result={"filename": plan.output.name, "size": size})
