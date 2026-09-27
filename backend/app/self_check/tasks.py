from collections.abc import AsyncGenerator
from contextlib import aclosing

from ..background_tasks import TaskProgress, TaskType, get_task_manager
from ..background_tasks.api_models import TaskAccepted
from ..operations.journal_types import ResourceReference
from .constants import MANUAL_TRIGGER
from .service import get_self_check_service


async def self_check_task(actor_id: int, check_id: str | None) -> AsyncGenerator[TaskProgress]:
    service = get_self_check_service()
    findings: list[dict] = []
    completed = 0
    total = 1
    started_at = None
    async with aclosing(service.iter_self_check_events(
        trigger=MANUAL_TRIGGER, requested_by_user_id=actor_id,
        check_ids=(check_id,) if check_id else None, scope="check" if check_id else "full",
    )) as events:
        async for event in events:
            total = event.total_checks or total
            if event.started_at:
                started_at = event.started_at.isoformat()
            if event.findings:
                findings.extend(finding.model_dump(mode="json") for finding in event.findings)
            if event.type == "check_finished":
                completed += 1
            result = event.result.model_dump(mode="json") if event.result else {
                "id": event.run_id, "findings": list(findings), "check_id": event.check_id,
                "started_at": started_at, "checking": event.type == "check_started",
                "completed_checks": completed, "total_checks": total,
            }
            title = service.validate_check_id(event.check_id).title if event.check_id else "自检"
            yield TaskProgress(
                progress=100 if event.result else completed / total * 100,
                message="自检完成，请查看检查结果" if event.result else f"正在检查：{title}",
                result=result,
            )


async def submit_self_check(actor_id: int, check_id: str | None = None) -> TaskAccepted:
    submitted = await get_task_manager().submit_durable(
        TaskType.SELF_CHECK, "运行自检" if check_id is None else f"自检：{get_self_check_service().validate_check_id(check_id).title}",
        self_check_task(actor_id, check_id), actor_id=actor_id, cancellable=False,
        resources=(ResourceReference("diagnostics"),), exclusive_key="manual-self-check",
    )
    return TaskAccepted(task_id=submitted.task_id)
