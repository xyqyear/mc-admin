from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, TypeAdapter
from pydantic_core import PydanticSerializationError

from app.background_tasks.models import BackgroundTask
from app.background_tasks.types import TaskStatus, TaskType
from app.operations.changes import OperationChanges

MAX_INLINE_RESULT_BYTES = 16 * 1024
MAX_EVENT_PROGRESS_BYTES = 8 * 1024
MAX_TERMINAL_PROGRESS_BYTES = 1024
_result_adapter = TypeAdapter(dict[str, Any] | None)
_progress_adapter = TypeAdapter(dict[str, Any])


def _event_progress_details(task: BackgroundTask) -> dict[str, Any] | None:
    details = task.progress_details
    if details is None:
        return None
    terminal = task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING)
    cached = task._event_progress_cache
    if cached is not None and cached[0] is details and cached[1] == terminal:
        return cached[2]
    budget = MAX_TERMINAL_PROGRESS_BYTES if terminal else MAX_EVENT_PROGRESS_BYTES
    try:
        if not terminal and len(_progress_adapter.dump_json(details)) <= budget:
            task._event_progress_cache = (details, terminal, details)
            return details
    except PydanticSerializationError:
        pass
    projected: dict[str, Any] = {"truncated": True}
    if details.get("kind") == "self_check":
        findings = details.get("findings")
        projected.update(findings=[], findings_total=len(findings) if isinstance(findings, list) else 0,
                         findings_truncated=bool(findings))
    keys = dict.fromkeys(("kind", "id", "check_id", "started_at", "checking", "completed_checks", "total_checks", "findings_total", *details))
    for key in keys:
        if key not in details or key in {"truncated", "findings_truncated"}:
            continue
        value = details[key]
        if not isinstance(value, (str, int, float, bool, type(None))):
            continue
        candidate = {**projected, key: value}
        if len(_progress_adapter.dump_json(candidate)) <= budget:
            projected = candidate
    if not terminal:
        for key, value in details.items():
            if not isinstance(value, list):
                continue
            retained: list[Any] = []
            for item in value:
                candidate = {**projected, key: [*retained, item]}
                try:
                    if len(_progress_adapter.dump_json(candidate)) > budget:
                        continue
                except PydanticSerializationError:
                    continue
                retained.append(item)
                projected = candidate
            if key == "findings" and len(retained) != len(value):
                projected["findings_truncated"] = True
    if {key: value for key, value in projected.items() if key != "truncated"} == details:
        projected.pop("truncated")
    task._event_progress_cache = (details, terminal, projected)
    return projected


class TaskAccepted(BaseModel):
    task_id: str


class BackgroundTaskSummaryResponse(BaseModel):
    """Lightweight API response model for task lists."""

    task_id: str
    task_type: TaskType
    name: str
    status: TaskStatus
    progress: float | None
    message: str
    progress_details: dict[str, Any] | None = None
    server_id: str | None
    cancellable: bool
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    error: str | None
    error_code: str | None = None

    @classmethod
    def from_task(cls, task: BackgroundTask) -> Self:
        return cls.model_validate(task, from_attributes=True)


class BackgroundTaskResponse(BackgroundTaskSummaryResponse):
    """API response model for a background task."""

    result: dict[str, Any] | None


class BackgroundTaskListResponse(BaseModel):
    """API response model for a list of background tasks."""

    tasks: list[BackgroundTaskSummaryResponse]
    total: int


class BackgroundTaskEventResponse(BackgroundTaskSummaryResponse):
    result_included: bool = False
    result: dict[str, Any] | None = None

    @classmethod
    def from_task(cls, task: BackgroundTask) -> Self:
        response = cls(**{name: getattr(task, name) for name in BackgroundTaskSummaryResponse.model_fields})
        response.progress_details = _event_progress_details(task)
        if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING) or not task.result_known:
            return response
        cached = task._event_result_cache
        if cached is None or cached[0] is not task.result:
            try:
                included = len(_result_adapter.dump_json(task.result)) <= MAX_INLINE_RESULT_BYTES
            except PydanticSerializationError:
                included = False
            task._event_result_cache = (task.result, included)
        else:
            included = cached[1]
        if included:
            response.result_included = True
            response.result = task.result
        return response


class TaskSnapshotEvent(BaseModel):
    type: Literal["snapshot"] = "snapshot"
    tasks: list[BackgroundTaskEventResponse]
    active_restorations: list[dict[str, Any]]
    prune_states: list[dict[str, Any]]


class TaskUpsertEvent(BaseModel):
    type: Literal["upsert"] = "upsert"
    task: BackgroundTaskEventResponse


class TaskRemoveEvent(BaseModel):
    type: Literal["remove"] = "remove"
    task_id: str


class OperationChangesEvent(BaseModel):
    type: Literal["operation_changes"] = "operation_changes"
    changes: OperationChanges


class RestorationIndexEvent(BaseModel):
    type: Literal["restoration_index"] = "restoration_index"
    active_restorations: list[dict[str, Any]]


class PruneStateEvent(BaseModel):
    type: Literal["prune_state"] = "prune_state"
    prune_states: list[dict[str, Any]]
