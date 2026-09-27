from collections.abc import AsyncGenerator

from ..background_tasks import TaskProgress, TaskType, get_task_manager
from ..background_tasks.api_models import TaskAccepted
from ..db.database import get_async_session
from ..operations.context import record_phase
from ..operations.journal_types import ResourceReference
from .manager import get_dns_manager


async def update_task() -> AsyncGenerator[TaskProgress]:
    yield TaskProgress(message="正在核对并更新 DNS 和路由")
    await record_phase("updating_dns", changed=True)
    async with get_async_session() as session:
        await get_dns_manager().update(session)
    yield TaskProgress(progress=100, message="DNS 和路由更新完成", result={"success": True, "message": "DNS 和路由更新完成"})


async def submit_update(actor_id: int) -> TaskAccepted:
    submitted = await get_task_manager().submit_durable(
        TaskType.DNS_UPDATE, "更新 DNS 和路由", update_task(), actor_id=actor_id,
        resources=(ResourceReference("connectivity"),), cancellable=False, exclusive_key="dns-update",
    )
    return TaskAccepted(task_id=submitted.task_id)
