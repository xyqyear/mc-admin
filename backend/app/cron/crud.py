from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CronJob, CronJobExecution, CronJobStatus


async def get_cronjob(session: AsyncSession, cronjob_id: str) -> Optional[CronJob]:
    result = await session.execute(
        select(CronJob).where(CronJob.cronjob_id == cronjob_id)
    )
    return result.scalar_one_or_none()


async def create_cronjob(
    session: AsyncSession,
    *,
    cronjob_id: str,
    identifier: str,
    name: str,
    cron: str,
    params_json: str,
    second: Optional[str] = None,
) -> None:
    cronjob = CronJob(
        cronjob_id=cronjob_id,
        identifier=identifier,
        name=name,
        cron=cron,
        second=second,
        params_json=params_json,
        status=CronJobStatus.ACTIVE,
    )
    session.add(cronjob)
    await session.commit()


async def update_cronjob(
    session: AsyncSession, cronjob_id: str, **values: Any
) -> None:
    values["updated_at"] = datetime.now(timezone.utc)
    await session.execute(
        update(CronJob).where(CronJob.cronjob_id == cronjob_id).values(**values)
    )
    await session.commit()


async def get_all_cronjobs(
    session: AsyncSession,
    *,
    identifier: Optional[str] = None,
    status: Optional[List[CronJobStatus]] = None,
    name: Optional[str] = None,
) -> List[CronJob]:
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
) -> List[CronJob]:
    result = await session.execute(
        select(CronJob).where(CronJob.status == status)
    )
    return list(result.scalars().all())


async def get_active_restart_cronjobs_for_server(
    session: AsyncSession, server_id: str
) -> List[CronJob]:
    result = await session.execute(
        select(CronJob).where(
            CronJob.identifier == "restart_server",
            CronJob.status == CronJobStatus.ACTIVE,
            func.json_extract(CronJob.params_json, "$.server_id") == server_id,
        )
    )
    return list(result.scalars().all())


async def get_execution_history(
    session: AsyncSession, cronjob_id: str, limit: int = 50
) -> List[CronJobExecution]:
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


async def increment_execution_count(
    session: AsyncSession, cronjob_id: str
) -> None:
    await session.execute(
        update(CronJob)
        .where(CronJob.cronjob_id == cronjob_id)
        .values(execution_count=CronJob.execution_count + 1)
    )
    await session.commit()
