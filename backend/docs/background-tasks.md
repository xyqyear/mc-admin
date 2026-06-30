# Background Tasks (`app.background_tasks`)

In-memory async-task manager for long-running operations the user wants to track. Used for archive compression / extraction, server populate, server rebuild, file ownership repair, and the world-restore flows that stage data before a restore. Not persisted — restarting the backend cancels everything in flight, by design.

## Why generators, not coroutines

Long operations need to report incremental progress to the UI. A coroutine that returns a final result can't do that without callbacks. An async generator that yields `TaskProgress` is the natural shape: each `yield` is a progress update; the last yield (or `return result`) is the terminal value.

```python
from app.background_tasks import task_manager, TaskType, TaskProgress

async def my_operation() -> AsyncGenerator[TaskProgress, None]:
    yield TaskProgress(progress=0, message="Starting…")
    # … do work, yield progress along the way …
    yield TaskProgress(progress=100, message="Done", result={"file_count": 42})

result = task_manager.submit(
    task_type=TaskType.ARCHIVE_CREATE,
    name="Compress survival_2025-05-10.7z",
    task_generator=my_operation(),
    server_id="survival",
    cancellable=True,
)
# result.task_id → returned to the frontend; poll /api/tasks/{id} for detail.
```

The manager wraps the generator in an `asyncio.Task`, intercepts each yield to update the in-memory `BackgroundTask` row, and resolves the `Future[TaskResult]` on the final yield. Cancellation flips the cooperative `cancel_requested` flag on the task; the generator is expected to check it and clean up.

## API

`BackgroundTaskManager` exposes:

- `submit(task_type, name, task_generator, server_id?, cancellable?) -> SubmitResult` — `SubmitResult` carries `task_id` and the `Future[TaskResult]` if you want to await locally instead of poll.
- `cancel(task_id) -> bool` — sets the cancellation flag.
- `get(task_id) -> BackgroundTask | None`.
- `get_tasks_by_server_id(server_id)` / `get_future(task_id)` — used by `app.servers.lifecycle` to cancel-and-wait on a server's in-flight tasks before rmtree, so an `ARCHIVE_EXTRACT` cannot race the directory deletion.
- `list(filters)` — listing with status / server / type filters.
- `cleanup(...)` — drop completed/failed entries past their TTL.

## Types

`TaskType` (in `types.py`):

- `ARCHIVE_CREATE` / `ARCHIVE_EXTRACT` — archive compression / extraction
- `FILE_OWNERSHIP_REPAIR` — non-cancellable recursive `chown` for server data files
- `SERVER_REBUILD` — template-config update triggering compose rewrite + `docker compose up -d`
- `WORLD_RESTORE` — world-restore staging tasks (the SSE flows themselves are *not* background tasks; they stream live)

`TaskStatus`: `PENDING → RUNNING → COMPLETED | FAILED | CANCELLED`.

`TaskProgress`: `progress: float | None`, `message: str`, `result: dict | None`.

## REST API

Mounted at `/api/tasks/`:

- `GET /` — summary list with filters; `result` is omitted so task center
  polling never serializes feature-specific payloads.
- `GET /{id}` — detail including `result`; feature pages use this only when
  the result is intentionally small or is the feature's dedicated payload.
- `POST /{id}/cancel`
- `DELETE /{id}` — drop a finished entry from memory
- `DELETE /` — bulk cleanup

## Files

- `manager.py` — `BackgroundTaskManager`, `task_manager` singleton
- `models.py` — `BackgroundTask` Pydantic model
- `types.py` — `TaskType`, `TaskStatus`, `TaskProgress`, `TaskResult`, `SubmitResult`

Implementation guide for callers: `.claude/background-tasks-guide.md`.
