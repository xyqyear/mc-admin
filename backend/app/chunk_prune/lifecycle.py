import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiofiles.os as aioos

from ..background_tasks import TaskStatus, get_task_manager
from ..background_tasks.models import BackgroundTask
from ..dynamic_config import get_config
from ..errors import PublicOperationError, log_safe_error
from ..utils import async_fs
from ..world.artifacts import protected_artifacts, valid_artifact_id
from .inputs import PrunePreviewConflict
from .models import ChunkPrunePreviewState, ChunkPruneTaskMetadata

MAX_RETAINED_PREVIEWS = 128


class PrunePreviewRegistry:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.metadata: dict[str, ChunkPruneTaskMetadata] = {}
        self.now = lambda: datetime.now(UTC)
        self._janitor: asyncio.Task | None = None

    def expires_at(self, preview: ChunkPruneTaskMetadata) -> datetime | None:
        return preview.completed_at + timedelta(seconds=get_config().mcmap.prune_preview_ttl_seconds) if preview.completed_at else None

    def state(self, preview: ChunkPruneTaskMetadata) -> ChunkPrunePreviewState:
        expires = self.expires_at(preview)
        availability = "building"
        task = self.task(preview)
        if preview.apply_task_id:
            availability = "consumed"
        elif preview.unavailable_reason:
            availability = preview.unavailable_reason
        elif expires is not None and self.now() >= expires:
            availability = "expired"
        elif preview.inputs is not None and preview.completed_at is not None:
            availability = "ready"
        elif task is not None and task.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
            availability = "unavailable"
        return ChunkPrunePreviewState.model_validate({
            "task_id": preview.task_id, "input_version": preview.inputs.version if preview.inputs else None,
            "expires_at": expires, "availability": availability, "apply_task_id": preview.apply_task_id,
        })

    def require_ready(self, preview: ChunkPruneTaskMetadata) -> None:
        state = self.state(preview).availability
        if state in {"expired", "stale", "consumed"}:
            raise PrunePreviewConflict(state)
        if state == "unavailable":
            raise PrunePreviewConflict("stale")

    @staticmethod
    def task(metadata: ChunkPruneTaskMetadata) -> BackgroundTask | None:
        return get_task_manager().get_task(metadata.task_id) or metadata.task

    def tasks(self, server_id: str) -> list[BackgroundTask]:
        tasks = {task.task_id: task for task in get_task_manager().get_all_tasks() if task.server_id == server_id}
        tasks.update({item.task_id: task for item in self.metadata.values()
                      if item.server_id == server_id and (task := self.task(item)) is not None})
        return list(tasks.values())

    async def reserve_capacity(self) -> None:
        await self.reap()
        previews = [item for item in self.metadata.values() if item.operation == "preview"]
        if len(previews) < MAX_RETAINED_PREVIEWS:
            return
        for preview in previews:
            task = self.task(preview)
            if preview.references or (task is not None and task.status in {TaskStatus.RUNNING, TaskStatus.PENDING}):
                continue
            if self.state(preview).availability in {"expired", "stale", "consumed", "unavailable"}:
                self.metadata.pop(preview.task_id, None)
                if preview.apply_task_id:
                    self.metadata.pop(preview.apply_task_id, None)
                return
        raise PublicOperationError("可用裁剪预览已达到上限，请等待预览过期或完成正在运行的任务")

    async def reap(self, *, closing: bool = False) -> None:
        protected = await protected_artifacts("prune_preview")
        if await aioos.path.isdir(self.base_dir):
            for path in await async_fs.iterdir(self.base_dir):
                if not valid_artifact_id(path.name) or path.name in protected or await aioos.path.islink(path):
                    continue
                preview = self.metadata.get(path.name)
                if preview is not None:
                    task = self.task(preview)
                    active = task is not None and task.status in {TaskStatus.RUNNING, TaskStatus.PENDING}
                    state = self.state(preview).availability
                    if preview.references or active or (not closing and state in {"ready", "building"}):
                        continue
                    preview.unavailable_reason = state if state in {"expired", "stale"} else "unavailable"
                    preview.geometry = None
                    preview.claims_file = None
                try:
                    await async_fs.rmtree(path, ignore_errors=False)
                except FileNotFoundError:
                    pass

    async def start(self) -> None:
        await aioos.makedirs(self.base_dir, exist_ok=True)
        await self.reap()
        if self._janitor is None or self._janitor.done():
            self._janitor = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(min(60, get_config().mcmap.prune_preview_ttl_seconds))
            try:
                await self.reap()
            except Exception as error:  # noqa: BLE001 - keep unrelated previews available after cleanup failure
                log_safe_error(error, "prune preview cleanup failed")

    async def close(self, *, preserve_artifacts: bool = False) -> None:
        if self._janitor is not None:
            self._janitor.cancel()
            await asyncio.gather(self._janitor, return_exceptions=True)
            self._janitor = None
        if not preserve_artifacts:
            await self.reap(closing=True)
            self.metadata.clear()
