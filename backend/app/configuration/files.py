import asyncio
import os
import stat
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from ..operations.context import current_execution
from ..operations.finalization import finalize
from ..operations.journal_types import RecoveryReference, ResourceReference
from ..utils import async_fs


def stage_path(project: Path, token: str) -> Path:
    return project / f".mc-admin-configuration-{token}.tmp"


def _write_stage(stage: Path, target: Path, content: bytes) -> None:
    metadata = target.stat()
    descriptor = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
        os.fchmod(stream.fileno(), stat.S_IMODE(metadata.st_mode))
        stream.flush()
        os.fsync(stream.fileno())


def _replace(stage: Path, target: Path) -> None:
    os.replace(stage, target)
    directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


@dataclass(frozen=True)
class StagedConfiguration:
    stage: Path
    target: Path

    async def replace(self) -> None:
        await finalize(asyncio.to_thread(_replace, self.stage, self.target))


@asynccontextmanager
async def staged_configuration(target: Path, content: bytes, *, project: Path | None = None) -> AsyncGenerator[StagedConfiguration]:
    project = await async_fs.resolve(project or target.parent)
    resolved = await async_fs.resolve_inside(project, target)
    token = uuid4().hex
    stage = stage_path(resolved.parent, token)
    execution = current_execution()
    try:
        if execution is not None:
            server = next(server for server in execution.servers if server.project_path == project)
            await execution.journal.retain_artifact(execution.operation_id, ResourceReference(
                "configuration_stage", server.server_id, server.generation, stage.relative_to(project).as_posix(),
            ))
            await execution.journal.phase(execution.operation_id, "staging_configuration", recovery_refs=(
                RecoveryReference("configuration_stage", token),
            ))
        await finalize(asyncio.to_thread(_write_stage, stage, resolved, content))
        yield StagedConfiguration(stage, resolved)
    finally:
        async def cleanup() -> None:
            await asyncio.to_thread(stage.unlink, missing_ok=True)
            if execution is not None:
                await execution.journal.resolve_reference(execution.operation_id, "configuration_stage", token)

        await finalize(cleanup())
