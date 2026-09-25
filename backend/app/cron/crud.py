import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.cron.models import CronJob, CronJobExecution, CronJobStatus, ExecutionStatus
from app.servers.models import Server, ServerStatus

from .bindings import RESTART_PURPOSE, binding_issue_message


async def get_cronjob(session: AsyncSession, cronjob_id: str) -> CronJob | None:
    result = await session.execute(
        select(CronJob).where(CronJob.cronjob_id == cronjob_id)
    )
    return result.scalar_one_or_none()


async def get_managed_restart_cronjob(
    session: AsyncSession, server_id: str
) -> CronJob | None:
    unresolved = await session.scalars(select(CronJob).where(
        CronJob.managed_purpose == RESTART_PURPOSE,
        CronJob.managed_binding_issue.is_not(None),
        CronJob.status != CronJobStatus.CANCELLED,
    ))
    for job in unresolved:
        try:
            params = json.loads(job.params_json)
        except (ValueError, TypeError):
            params = None
        if job.name == f"restart-{server_id}" or isinstance(params, dict) and params.get("server_id") == server_id:
            raise ValueError(
                f"服务器 '{server_id}' 的受管重启计划归属不明确："
                f"{binding_issue_message(job.managed_binding_issue or '')}（任务 {job.cronjob_id}）。"
                "请在定时任务中核对并取消有歧义的计划，再为当前服务器创建计划"
            )
    result = await session.execute(select(CronJob).join(
        Server, Server.id == CronJob.managed_server_generation,
    ).where(
        Server.server_id == server_id,
        Server.status == ServerStatus.ACTIVE,
        CronJob.managed_purpose == RESTART_PURPOSE,
    ))
    return result.scalar_one_or_none()


async def get_active_server_generation(session: AsyncSession, server_id: str) -> int:
    generation = await session.scalar(select(Server.id).where(
        Server.server_id == server_id, Server.status == ServerStatus.ACTIVE,
    ))
    if generation is None:
        raise ValueError("服务器实例未登记或已停用，不能创建受管重启计划")
    return generation


async def create_cronjob(
    session: AsyncSession,
    *,
    cronjob_id: str,
    identifier: str,
    name: str,
    cron: str,
    params_json: str,
    second: str | None = None,
    is_system: bool = False,
    managed_server_generation: int | None = None,
    managed_purpose: str | None = None,
) -> None:
    cronjob = CronJob(
        cronjob_id=cronjob_id,
        identifier=identifier,
        name=name,
        cron=cron,
        second=second,
        params_json=params_json,
        is_system=is_system,
        managed_server_generation=managed_server_generation,
        managed_purpose=managed_purpose,
        status=CronJobStatus.ACTIVE,
    )
    session.add(cronjob)
    await session.commit()


async def update_cronjob(
    session: AsyncSession, cronjob_id: str, **values: Any
) -> None:
    values["updated_at"] = datetime.now(UTC)
    await session.execute(
        update(CronJob).where(CronJob.cronjob_id == cronjob_id).values(**values)
    )
    await session.commit()


async def get_all_cronjobs(
    session: AsyncSession,
    *,
    identifier: str | None = None,
    status: list[CronJobStatus] | None = None,
    name: str | None = None,
) -> list[CronJob]:
    query = select(CronJob)

    if identifier:
        query = query.where(CronJob.identifier == identifier)
    if status:
        query = query.where(CronJob.status.in_(status))
    if name:
        query = query.where(CronJob.name.ilike(f"%{name}%"))

    query = query.order_by(CronJob.created_at.desc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_cronjobs_by_status(
    session: AsyncSession, status: CronJobStatus
) -> list[CronJob]:
    result = await session.execute(
        select(CronJob).where(CronJob.status == status)
    )
    return list(result.scalars().all())


async def get_active_restart_cronjobs_for_server(
    session: AsyncSession, server_id: str
) -> list[CronJob]:
    result = await session.execute(
        select(CronJob).where(
            CronJob.identifier == "restart_server",
            CronJob.status == CronJobStatus.ACTIVE,
        )
    )
    generation = await session.scalar(select(Server.id).where(
        Server.server_id == server_id, Server.status == ServerStatus.ACTIVE,
    ))
    owned = []
    for job in result.scalars():
        if job.managed_purpose is not None:
            if job.managed_purpose == RESTART_PURPOSE and generation is not None and job.managed_server_generation == generation:
                owned.append(job)
            continue
        try:
            params = json.loads(job.params_json)
        except (ValueError, TypeError):
            continue
        if isinstance(params, dict) and params.get("server_id") == server_id:
            owned.append(job)
    return owned


async def get_execution_history(
    session: AsyncSession, cronjob_id: str, limit: int = 50
) -> list[CronJobExecution]:
    result = await session.execute(
        select(CronJobExecution)
        .where(CronJobExecution.cronjob_id == cronjob_id)
        .order_by(CronJobExecution.started_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def create_execution_record(
    session: AsyncSession, record_data: dict
) -> None:
    execution = CronJobExecution(**record_data)
    session.add(execution)
    await session.commit()


async def finish_execution_record(session: AsyncSession, record_data: dict) -> None:
    finished_job = await session.scalar(
        update(CronJobExecution).where(
            CronJobExecution.execution_id == record_data["execution_id"],
            CronJobExecution.status == ExecutionStatus.RUNNING,
        ).values(**record_data).returning(CronJobExecution.cronjob_id)
    )
    if finished_job is not None:
        await session.execute(update(CronJob).where(
            CronJob.cronjob_id == finished_job,
        ).values(execution_count=CronJob.execution_count + 1))
    await session.commit()


async def interrupt_running_executions(session: AsyncSession) -> None:
    rows = list(await session.scalars(select(CronJobExecution).where(
        CronJobExecution.status == ExecutionStatus.RUNNING,
    )))
    ended_at = datetime.now(UTC)
    for row in rows:
        try:
            messages = json.loads(row.messages_json)
        except (ValueError, TypeError):
            messages = []
        if not isinstance(messages, list):
            messages = []
        messages.append("应用重启前的定时任务已中断，请查看操作历史")
        started_at = row.started_at.replace(tzinfo=UTC) if row.started_at.tzinfo is None else row.started_at
        await finish_execution_record(session, {
            "execution_id": row.execution_id,
            "status": ExecutionStatus.FAILED,
            "ended_at": ended_at,
            "duration_ms": max(0, int((ended_at - started_at).total_seconds() * 1000)),
            "messages_json": json.dumps(messages, ensure_ascii=False),
        })
