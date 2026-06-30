from app.background_tasks import TaskProgress, TaskType, task_manager
from app.routers.tasks import get_task, get_tasks


async def test_task_list_omits_result_payload():
    task_id = "task-list-summary-omits-result"
    task_manager.remove_task(task_id)

    async def task_gen():
        yield TaskProgress(
            progress=100,
            message="done",
            result={"large": ["payload"]},
        )

    submit = task_manager.submit(
        TaskType.CHUNK_PRUNE_PREVIEW,
        "summary test",
        task_gen(),
        task_id=task_id,
    )
    try:
        await submit.awaitable

        response = await get_tasks()
        listed = next(task for task in response.tasks if task.task_id == task_id)
        detail = await get_task(task_id)

        assert not hasattr(listed, "result")
        assert detail.result == {"large": ["payload"]}
    finally:
        task_manager.remove_task(task_id)
