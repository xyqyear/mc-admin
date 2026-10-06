import asyncio

from app.background_tasks.types import TaskStatus
from app.snapshots.restoration_models import RestorationStatus, RestorationType
from app.snapshots.scopes import WorldScope
from app.snapshots.selection_models import RestorationSelection


async def complete(case, accepted, *, success=True):
    future = case.tasks.get_future(accepted["task_id"])
    assert future is not None
    result = await asyncio.wait_for(asyncio.shield(future), 30)
    assert result.success is success, result
    task = case.tasks.get_task(accepted["task_id"])
    assert task.status is (TaskStatus.COMPLETED if success else TaskStatus.FAILED), task
    if accepted.get("restoration_id"):
        row = await case.commands.store.get(accepted["restoration_id"])
        assert row.operation_id == accepted["task_id"]
        assert row.status is (
            RestorationStatus.SUCCEEDED if success else RestorationStatus.FAILED
        )
    return result.data


def scope(kind="world"):
    return WorldScope(
        server_id="survival",
        selection=RestorationSelection(
            type=RestorationType(kind),
            region_dir_relpath=None if kind == "world" else "world/region",
            regions=[(0, 0)] if kind == "regions" else [],
            chunks=[(0, 0)] if kind == "chunks" else [],
        ),
    )


async def create(case, target=None):
    return (await complete(case, await case.commands.create(target or scope(), 1)))[
        "snapshot"
    ]["id"]
