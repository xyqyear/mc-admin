from typing import Any, Literal

from .background_tasks.types import TaskType
from .runtime_resources import current_runtime
from .snapshots.queries import RestorationQueries


async def snapshot(domain: Literal["restorations", "prune"]) -> list[dict[str, Any]]:
    runtime = current_runtime()
    if domain == "restorations":
        active = {task.task_id: task.status.value for task in runtime.task_manager.get_active_tasks()
                  if task.task_type is TaskType.SNAPSHOT_RESTORE}
        return await RestorationQueries(runtime.session_factory).observation_index(active)
    return runtime.chunk_prune_service.registry.observation_index()
