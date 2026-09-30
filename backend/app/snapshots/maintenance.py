from collections.abc import AsyncGenerator
from contextlib import ExitStack

from ..background_tasks import TaskProgress, TaskType
from ..background_tasks.manager import BackgroundTaskManager
from ..operations.context import record_phase
from ..operations.execution import settle_before_release
from .service import SnapshotService


class SnapshotMaintenance:
    def __init__(
        self, snapshots: SnapshotService, tasks: BackgroundTaskManager
    ) -> None:
        self._snapshots = snapshots
        self._tasks = tasks

    async def submit(self, actor_id: int, *, snapshot_id: str | None = None) -> dict:
        with ExitStack() as stack:
            reservation = stack.enter_context(self._snapshots.repository_use.maintain())
            submitted = await self._tasks.submit_durable(
                TaskType.SNAPSHOT_DELETE if snapshot_id else TaskType.SNAPSHOT_UNLOCK,
                "删除快照并回收空间" if snapshot_id else "清理失效的快照仓库锁",
                self._execute(snapshot_id, reservation),
                actor_id=actor_id,
                exclusive_key="snapshot-repository-maintenance",
            )
            retained = stack.pop_all()
            submitted.awaitable.add_done_callback(lambda _: retained.close())
        return {"task_id": submitted.task_id}

    async def _execute(
        self, snapshot_id: str | None, reservation: object
    ) -> AsyncGenerator[TaskProgress]:
        async with settle_before_release():
            if snapshot_id:
                yield TaskProgress(message="正在删除快照并回收仓库空间")
                await record_phase("deleting_snapshot")
                await self._snapshots.forget_id(
                    snapshot_id, prune=True, reservation=reservation
                )
                message = "快照已删除，仓库空间已回收"
                result = {"message": message}
            else:
                yield TaskProgress(message="正在检查并清理失效的仓库锁")
                await record_phase("unlocking_repository")
                output = await self._snapshots.unlock(reservation=reservation)
                message = "失效的仓库锁已清理；仍在使用的锁会保留"
                result = {"message": message, "output": output[:8192]}
            yield TaskProgress(progress=100, message=message, result=result)
