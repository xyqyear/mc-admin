"""Admission of cache writers after durable ownership reconciliation."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from ..db.database import get_async_session
from ..operations.context import current_execution
from ..operations.finalization import finalize
from ..runtime_resources import current_runtime
from ..servers.references import resolve_server_ref
from ..utils import async_fs


@dataclass(frozen=True)
class PreviewRenderTarget:
    server_id: str
    generation: int
    session_id: str
    session_dir: Path

    async def validate(self, data_path: Path) -> None:
        from ..world.artifacts import valid_artifact_id

        if not valid_artifact_id(self.session_id) or self.session_dir.name != self.session_id:
            raise ValueError("Invalid preview artifact identity")
        execution = current_execution()
        if execution is not None:
            reference = next((server for server in execution.servers if server.server_id == self.server_id), None)
            if reference is None or reference.generation != self.generation or reference.data_path != await async_fs.resolve(data_path):
                raise HTTPException(status_code=409, detail="预览所属服务器实例已变化，请重新创建预览")

    @asynccontextmanager
    async def retained(self) -> AsyncGenerator[None]:
        from ..world.artifacts import release_artifact, retain_artifact

        try:
            await retain_artifact("world_preview", self.session_id)
            yield
        finally:
            await finalize(release_artifact("world_preview", self.session_id))


async def require_usable_cache(server_id: str) -> None:
    runtime = current_runtime()
    recovery = runtime.resources.get("operation_recovery")
    if recovery is None or not any(resource.server_id == server_id for resource in recovery.degraded_resources):
        return
    async with get_async_session() as db:
        reference = await resolve_server_ref(db, server_id, servers_root=runtime.settings.server_path)
    if any(resource.server_id == server_id and resource.generation == reference.generation for resource in recovery.degraded_resources):
        raise HTTPException(status_code=503, detail="地图缓存需要重新验证，请处理操作历史中的缓存恢复")
