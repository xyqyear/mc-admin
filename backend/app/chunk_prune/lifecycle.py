import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiofiles.os as aioos

from ..background_tasks import TaskStatus, get_task_manager
from ..background_tasks.api_models import BackgroundTaskEventResponse
from ..background_tasks.models import BackgroundTask
from ..background_tasks.types import TaskType
from ..dynamic_config import get_config, get_config_manager
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
        self._expiry: asyncio.Task | None = None
        self._expiry_changed = asyncio.Event()
        self._unlisten_config: Callable[[], None] | None = None

    def changed(self) -> None:
        get_task_manager().notify_observation("prune")
        self._expiry_changed.set()

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

    def observation_index(self) -> list[dict[str, Any]]:
        tasks = {task.task_id: task for task in get_task_manager().get_all_tasks()
                 if task.task_type in {TaskType.CHUNK_PRUNE_PREVIEW, TaskType.CHUNK_PRUNE_APPLY}}
        tasks.update({item.task_id: task for item in self.metadata.values()
                      if (task := self.task(item)) is not None})
        latest: dict[str, dict[TaskType, BackgroundTask]] = {}
        for task in tasks.values():
            if task.server_id is None:
                continue
            server_tasks = latest.setdefault(task.server_id, {})
            previous = server_tasks.get(task.task_type)
            if previous is None or task.created_at > previous.created_at:
                server_tasks[task.task_type] = task
        result = []
        for server_id, server_tasks in sorted(latest.items()):
            preview_task = server_tasks.get(TaskType.CHUNK_PRUNE_PREVIEW)
            apply_task = server_tasks.get(TaskType.CHUNK_PRUNE_APPLY)
            if preview_task is None or (apply_task is not None and apply_task.created_at < preview_task.created_at):
                apply_task = None
            metadata = self.metadata.get(preview_task.task_id) if preview_task is not None else None
            result.append({
                "server_id": server_id,
                "preview_task": BackgroundTaskEventResponse.from_task(preview_task).model_dump(mode="json") if preview_task is not None else None,
                "apply_task": BackgroundTaskEventResponse.from_task(apply_task).model_dump(mode="json") if apply_task is not None else None,
                "preview": self.state(metadata).model_dump(mode="json") if metadata is not None else None,
            })
        return result

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
                self.changed()
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
                    self.changed()
                try:
                    await async_fs.rmtree(path, ignore_errors=False)
                except FileNotFoundError:
                    pass

    async def start(self) -> None:
        await aioos.makedirs(self.base_dir, exist_ok=True)
        await self.reap()
        if self._unlisten_config is None:
            self._unlisten_config = get_config_manager().listen("mcmap", self.changed)
        if self._janitor is None or self._janitor.done():
            self._janitor = asyncio.create_task(self._loop())
        if self._expiry is None or self._expiry.done():
            self._expiry = asyncio.create_task(self._expiry_loop())

    async def _expiry_loop(self) -> None:
        previous = None
        while True:
            self._expiry_changed.clear()
            previews = [item for item in self.metadata.values() if item.operation == "preview"]
            states = [self.state(preview) for preview in previews]
            signature = tuple((state.task_id, state.expires_at, state.availability, state.apply_task_id)
                              for state in states)
            if signature != previous:
                get_task_manager().notify_observation("prune")
                previous = signature
            deadlines = [state.expires_at for state in states
                         if state.availability == "ready" and state.expires_at is not None]
            if not deadlines:
                await self._expiry_changed.wait()
                continue
            delay = max(0, (min(deadlines) - self.now()).total_seconds())
            try:
                await asyncio.wait_for(self._expiry_changed.wait(), delay)
            except TimeoutError:
                pass

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(min(60, get_config().mcmap.prune_preview_ttl_seconds))
            try:
                await self.reap()
            except Exception as error:  # noqa: BLE001 - keep unrelated previews available after cleanup failure
                log_safe_error(error, "prune preview cleanup failed")
            self._expiry_changed.set()

    async def close(self, *, preserve_artifacts: bool = False) -> None:
        if self._unlisten_config is not None:
            self._unlisten_config()
            self._unlisten_config = None
        if self._expiry is not None:
            self._expiry.cancel()
            await asyncio.gather(self._expiry, return_exceptions=True)
            self._expiry = None
        if self._janitor is not None:
            self._janitor.cancel()
            await asyncio.gather(self._janitor, return_exceptions=True)
            self._janitor = None
        if not preserve_artifacts:
            await self.reap(closing=True)
            self.metadata.clear()
