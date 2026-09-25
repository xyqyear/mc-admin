import asyncio
from collections.abc import AsyncGenerator, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel

from ..errors import log_safe_error, public_error_code, public_error_message
from ..logger import get_logger
from ..operation_admission import get_server_write_admission
from ..operations.finalization import finalize
from ..runtime_resources import current_runtime
from .models import BackgroundTask
from .types import TaskProgress, TaskResult, TaskStatus, TaskType

if TYPE_CHECKING:
    from ..operations.coordinator import ResourceClaim
    from ..operations.journal import OperationJournal
    from ..operations.journal_types import OperationRecord


class SubmitResult(BaseModel):
    """Result returned when submitting a task."""

    model_config = {"arbitrary_types_allowed": True}

    task_id: str
    task: BackgroundTask
    awaitable: asyncio.Future[TaskResult]


class BackgroundTaskManager:
    """Manager for background tasks. Singleton instance."""

    def __init__(self, journal: "OperationJournal | None" = None):
        self._tasks: dict[str, BackgroundTask] = {}
        self._asyncio_tasks: dict[str, asyncio.Task] = {}
        self._futures: dict[str, asyncio.Future[TaskResult]] = {}
        self._accepting = True
        self.journal = journal

    async def submit_durable(
        self,
        task_type: TaskType,
        name: str,
        task_generator: AsyncGenerator[TaskProgress],
        server_id: str | None = None,
        cancellable: bool = True,
        task_id: str | None = None,
        *,
        actor_id: int | None = None,
        configuration_version: str | None = None,
        claims: Sequence["ResourceClaim"] | None = None,
    ) -> SubmitResult:
        if self.journal is None:
            return self.submit(task_type=task_type, name=name, task_generator=task_generator, server_id=server_id, cancellable=cancellable, task_id=task_id)
        from ..config import get_settings
        settings = get_settings()
        from ..db.database import get_async_session
        from ..operations.context import (
            OperationExecution,
            bind_execution,
            revalidate_targets,
        )
        from ..operations.execution import accept_operation
        from ..operations.journal_types import (
            OperationSpec,
            OperationState,
            ResourceReference,
        )
        from ..operations.resources import journal_resources
        from ..servers.references import resolve_server_ref

        servers = ()
        if server_id is not None:
            get_server_write_admission().check(server_id)
            async with get_async_session() as db:
                servers = (await resolve_server_ref(db, server_id, servers_root=settings.server_path),)
        task_id = task_id or str(uuid4())
        resource_kind = {
            TaskType.SERVER_REBUILD: "configuration",
            TaskType.CHUNK_PRUNE_APPLY: "world",
            TaskType.CHUNK_PRUNE_PREVIEW: "cache",
            TaskType.WORLD_RESTORE: "world",
            TaskType.ARCHIVE_EXTRACT: "files",
            TaskType.FILE_OWNERSHIP_REPAIR: "files",
        }.get(task_type, "server")
        resources = tuple(ResourceReference(resource_kind, ref.server_id, ref.generation) for ref in servers) or (ResourceReference("archive"),)
        if claims is not None:
            resources = journal_resources(servers, claims, default_kind=resource_kind, empty_kind="archive")
        try:
            record = await accept_operation(self.journal, OperationSpec(
                kind=task_type.value, resources=resources, actor_id=actor_id, origin="task",
                name=name.encode()[:200].decode(errors="ignore"), operation_id=task_id, legacy_id=task_id,
                configuration_version=configuration_version,
            ))
        except BaseException as failure:
            try:
                await finalize(task_generator.aclose())
            except BaseException as cleanup_failure:
                raise failure from cleanup_failure
            raise
        execution = OperationExecution(self.journal, record.operation_id, servers)

        async def durable_generator() -> AsyncGenerator[TaskProgress]:
            state = OperationState.FAILED
            with bind_execution(execution):
                try:
                    await execution.journal.start(record.operation_id)
                    await revalidate_targets()
                    async for progress in task_generator:
                        yield progress
                    state = OperationState.SUCCEEDED
                except (asyncio.CancelledError, GeneratorExit):
                    state = OperationState.CANCELLED
                    raise
                except Exception as error:
                    execution.failure_code = public_error_code(error)
                    raise
                finally:
                    async def cleanup() -> None:
                        nonlocal state
                        try:
                            await task_generator.aclose()
                        except BaseException:
                            state = OperationState.FAILED
                            raise
                        finally:
                            from ..operations.execution import settle_execution

                            await settle_execution(execution, state)
                    await finalize(cleanup())

        try:
            return self.submit(task_type, name, durable_generator(), server_id, cancellable, task_id)
        except BaseException as failure:
            async def reject_submission() -> None:
                try:
                    await task_generator.aclose()
                finally:
                    await execution.journal.finish(record.operation_id, OperationState.FAILED, writers_stopped=True)
            try:
                await finalize(reject_submission())
            except BaseException as cleanup_failure:
                raise failure from cleanup_failure
            raise

    def restore_history(self, records: Sequence["OperationRecord"]) -> None:
        from ..operations.journal_types import OperationState

        for record in records:
            if record.origin != "task" or not record.legacy_id:
                continue
            try:
                task_type = TaskType(record.kind)
            except ValueError:
                continue
            state = {
                OperationState.SUCCEEDED: TaskStatus.COMPLETED,
                OperationState.CANCELLED: TaskStatus.CANCELLED,
            }.get(record.state, TaskStatus.FAILED)
            interrupted = record.state is OperationState.INTERRUPTED
            message = "应用重启前的操作已中断，请查看操作历史" if interrupted else "操作记录已恢复"
            self._tasks[record.legacy_id] = BackgroundTask(
                task_id=record.legacy_id, task_type=task_type, name=record.name,
                server_id=next((resource.server_id for resource in record.resources if resource.server_id), None),
                status=state, message=message, created_at=record.created_at,
                ended_at=record.ended_at, error=message if state is TaskStatus.FAILED else None,
                error_code=record.failure_code,
                cancellable=False,
            )

    def submit(
        self,
        task_type: TaskType,
        name: str,
        task_generator: AsyncGenerator[TaskProgress],
        server_id: str | None = None,
        cancellable: bool = True,
        task_id: str | None = None,
    ) -> SubmitResult:
        """
        Submit a background task.

        Args:
            task_type: Type of the task
            name: Display name for the task
            task_generator: Instantiated async generator that yields TaskProgress
            server_id: Associated server ID, or None for global tasks
            cancellable: Whether the task can be cancelled

        Returns:
            SubmitResult containing task_id and an awaitable Future

        Example:
            async def compress_task(path: str):
                for i in range(100):
                    yield TaskProgress(progress=i, message=f"Processing {i}%")
                yield TaskProgress(progress=100, message="Done", result={"size": 1024})

            result = manager.submit(
                TaskType.ARCHIVE_CREATE,
                "backup.7z",
                compress_task("/data"),
                server_id="survival"
            )
            # Immediate return
            return {"task_id": result.task_id}

            # Or wait for completion
            task_result = await result.awaitable
        """
        logger = get_logger()
        if not self._accepting:
            raise RuntimeError("后台任务管理器正在关闭")
        if server_id is not None:
            get_server_write_admission().check(server_id)
        if task_id is not None and task_id in self._tasks:
            raise ValueError(f"Task {task_id} already exists")

        task_kwargs = {
            "task_type": task_type,
            "name": name,
            "server_id": server_id,
            "cancellable": cancellable,
        }
        if task_id is not None:
            task_kwargs["task_id"] = task_id
        task = BackgroundTask(**task_kwargs)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[TaskResult] = loop.create_future()

        self._tasks[task.task_id] = task
        self._futures[task.task_id] = future

        async def run_task():
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(UTC).astimezone().replace(tzinfo=None)
            terminal = TaskStatus.COMPLETED
            error: str | None = None
            try:
                if task.cancel_requested:
                    if self.journal is not None:
                        from ..operations.journal_types import OperationState

                        await self.journal.finish(task.task_id, OperationState.CANCELLED, writers_stopped=True)
                    raise asyncio.CancelledError
                async for progress in task_generator:
                    if task.cancel_requested:
                        raise asyncio.CancelledError
                    task.progress = progress.progress
                    task.message = progress.message
                    if progress.result is not None:
                        task.result = progress.result

            except asyncio.CancelledError:
                terminal = TaskStatus.CANCELLED
                error = "已取消"
            except Exception as e:  # noqa: BLE001 - task failures must not expose exception values
                terminal = TaskStatus.FAILED
                error = public_error_message(e)
                task.error_code = public_error_code(e)
                log_safe_error(e, f"Task {task.task_id} failed")
            finally:
                try:
                    await finalize(task_generator.aclose())
                except asyncio.CancelledError:
                    terminal = TaskStatus.CANCELLED
                    error = "已取消"
                except Exception as exc:  # noqa: BLE001 - cleanup failures must remain observable
                    terminal = TaskStatus.FAILED
                    error = public_error_message(exc)
                    log_safe_error(exc, f"Task {task.task_id} cleanup failed")
                async def publish_result() -> None:
                    logger = get_logger()
                    nonlocal terminal, error
                    if self.journal is not None:
                        from ..operations.journal_types import (
                            TERMINAL_STATES,
                            OperationState,
                        )

                        try:
                            recorded = await self.journal.get(task.task_id)
                        except Exception as exc:  # noqa: BLE001 - a failed journal read must still settle the task future
                            recorded = None
                            terminal = TaskStatus.FAILED
                            error = "无法确认持久化操作结果，请检查操作历史"
                            log_safe_error(exc, "Task result verification failed")
                        if recorded is not None and recorded.state in TERMINAL_STATES:
                            task.error_code = recorded.failure_code
                            terminal = {
                                OperationState.SUCCEEDED: TaskStatus.COMPLETED,
                                OperationState.CANCELLED: TaskStatus.CANCELLED,
                            }.get(recorded.state, TaskStatus.FAILED)
                            if terminal is TaskStatus.COMPLETED:
                                error = None
                            elif terminal is TaskStatus.CANCELLED:
                                error = "已取消"
                            elif error is None or error == "已取消":
                                error = "操作未完成，请查看操作历史中的恢复说明"
                    task.status = terminal
                    task.ended_at = datetime.now(UTC).astimezone().replace(tzinfo=None)
                    task.error = error if terminal is TaskStatus.FAILED else None
                    if terminal is TaskStatus.CANCELLED:
                        task.message = "已取消"
                    if terminal is TaskStatus.COMPLETED and task.progress is not None:
                        task.progress = 100
                    if not future.done():
                        future.set_result(TaskResult(
                            success=terminal is TaskStatus.COMPLETED,
                            data=task.result if terminal is TaskStatus.COMPLETED else None,
                            error=error,
                        ))
                    logger.info("Task %s settled: %s", task.task_id, terminal.value)
                await finalize(publish_result())

        from ..operations.context import bind_execution

        with bind_execution(None):
            asyncio_task = asyncio.create_task(run_task())
        self._asyncio_tasks[task.task_id] = asyncio_task
        logger.info(
            f"Task {task.task_id} ({task.name}) submitted, type={task_type.value}, server_id={server_id}"
        )

        return SubmitResult(task_id=task.task_id, task=task, awaitable=future)

    async def cancel(self, task_id: str) -> bool:
        """Request cancellation of a task."""
        logger = get_logger()
        task = self._tasks.get(task_id)
        if not task or not task.cancellable:
            return False
        if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            return False
        if task.cancel_requested:
            return True
        task.cancel_requested = True
        task.message = "正在取消，等待清理完成"
        worker = self._asyncio_tasks.get(task_id)
        if task.started_at is not None and worker is not None:
            worker.cancel()
        logger.info(f"Cancel requested for task {task_id} ({task.name})")
        return True

    async def shutdown(self) -> None:
        self._accepting = False
        workers = list(self._asyncio_tasks.values())
        for task in self.get_active_tasks():
            task.cancel_requested = True
            worker = self._asyncio_tasks.get(task.task_id)
            if task.started_at is not None and worker is not None and not worker.done():
                worker.cancel()
        if workers:
            await finalize(asyncio.gather(*workers, return_exceptions=True))

    def get_task(self, task_id: str) -> BackgroundTask | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[BackgroundTask]:
        """Get all tasks."""
        return list(self._tasks.values())

    def get_active_tasks(self) -> list[BackgroundTask]:
        """Get pending and running tasks."""
        return [
            t
            for t in self._tasks.values()
            if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
        ]

    def get_tasks_by_server_id(self, server_id: str) -> list[BackgroundTask]:
        """Get all pending/running tasks associated with a server."""
        return [
            t
            for t in self._tasks.values()
            if t.server_id == server_id
            and t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
        ]

    def get_future(self, task_id: str) -> asyncio.Future[TaskResult] | None:
        """Get the Future for a task, allowing external code to await completion."""
        return self._futures.get(task_id)

    def remove_task(self, task_id: str) -> bool:
        """Remove a completed task."""
        task = self._tasks.get(task_id)
        if not task:
            return False
        if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            return False
        del self._tasks[task_id]
        self._asyncio_tasks.pop(task_id, None)
        self._futures.pop(task_id, None)
        return True

    def clear_completed(self) -> int:
        """Clear all completed/failed/cancelled tasks."""
        to_remove = [
            tid
            for tid, t in self._tasks.items()
            if t.status not in (TaskStatus.PENDING, TaskStatus.RUNNING)
        ]
        for tid in to_remove:
            del self._tasks[tid]
            self._asyncio_tasks.pop(tid, None)
            self._futures.pop(tid, None)
        return len(to_remove)


def get_task_manager() -> BackgroundTaskManager:
    return current_runtime().resource('task_manager')
