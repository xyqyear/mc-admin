import hashlib
import re
import secrets
import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import aiofiles.os as aioos

from ..operations.context import current_execution, retain_recovery_reference
from ..operations.finalization import finalize
from ..runtime_resources import current_runtime
from ..utils import async_fs

ARTIFACT_REFERENCE_KINDS = {"world_preview", "prune_preview", "world_restore_stage"}


def artifact_root(feature: str) -> Path:
    runtime = current_runtime()
    identity = f"{runtime.settings.database_url}\0{runtime.settings.server_path.absolute()}"
    installation = hashlib.sha256(identity.encode()).hexdigest()
    return Path(tempfile.gettempdir()) / "mc-admin-world-artifacts" / installation / feature


def valid_artifact_id(value: str) -> bool:
    return re.fullmatch(r"[a-z0-9-]{16,80}", value) is not None


async def retain_artifact(kind: str, artifact_id: str) -> None:
    if kind not in ARTIFACT_REFERENCE_KINDS or not valid_artifact_id(artifact_id):
        raise ValueError("Invalid world artifact reference")
    await retain_recovery_reference(kind, artifact_id)


async def release_artifact(kind: str, artifact_id: str) -> None:
    execution = current_execution()
    if execution is not None:
        record = await execution.journal.get(execution.operation_id)
        if record is not None and record.ownership_known and not record.processes:
            await execution.journal.resolve_reference(execution.operation_id, kind, artifact_id)


async def protected_artifacts(kind: str) -> set[str]:
    journal = current_runtime().journal
    if journal is None:
        return set()
    protected: set[str] = set()
    offset = 0
    while records := await journal.list(limit=1000, offset=offset):
        protected.update(
            reference.value for record in records for reference in record.recovery_refs
            if reference.kind == kind and not reference.resolved
        )
        offset += len(records)
    return protected


@asynccontextmanager
async def restore_stage() -> AsyncGenerator[Path]:
    token = secrets.token_hex(16)
    path = artifact_root("restore-stage") / token
    active = current_runtime().resources.setdefault("world_restore_stages", set())
    active.add(token)
    try:
        await retain_artifact("world_restore_stage", token)
        await finalize(aioos.makedirs(path, exist_ok=False))
        yield path
    finally:
        async def cleanup() -> None:
            await release_artifact("world_restore_stage", token)
            active.discard(token)
            if token not in await protected_artifacts("world_restore_stage"):
                await async_fs.rmtree(path, ignore_errors=True)
        await finalize(cleanup())


async def reap_restore_stages() -> None:
    base = artifact_root("restore-stage")
    if not await aioos.path.isdir(base):
        return
    for path in await async_fs.iterdir(base):
        if not valid_artifact_id(path.name) or await aioos.path.islink(path):
            continue
        protected = await protected_artifacts("world_restore_stage")
        active = current_runtime().resources.get("world_restore_stages", set())
        if path.name not in active and path.name not in protected:
            try:
                await async_fs.rmtree(path, ignore_errors=False)
            except FileNotFoundError:
                pass
