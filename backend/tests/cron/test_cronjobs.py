"""Sample cron jobs for cron system tests; not registered in production."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import cast

from app.cron.registry import CronRegistry
from app.cron.types import ExecutionContext
from app.dynamic_config.schemas import BaseConfigSchema


class SampleCronJobParams(BaseConfigSchema):
    message: str = "Hello, World!"
    delay_seconds: int = 0


async def sample_cronjob(context: ExecutionContext):
    params: SampleCronJobParams = cast(SampleCronJobParams, context.params)

    context.log("Test cron job started")
    context.log(f"Received message: {params.message}")

    if params.delay_seconds > 0:
        context.log(f"Waiting {params.delay_seconds} seconds...")
        await asyncio.sleep(params.delay_seconds)

    context.log("Test cron job finished")

def create_test_registry() -> CronRegistry:
    registry = CronRegistry()
    registry.register_func(func=sample_cronjob, schema_cls=SampleCronJobParams, identifier="test_cronjob", description="Simple test cron job")
    return registry


def deferred_cron_expression():
    target = datetime.now(UTC) + timedelta(days=2)
    return f"0 0 {target.day} {target.month} *"


async def run_scheduled_once(manager, job_id, *, count=1, status="completed"):
    manager.scheduler.reschedule_job(job_id, trigger="date", run_date=datetime.now(UTC))
    async with asyncio.timeout(5):
        while True:
            history = await manager.get_execution_history(job_id)
            terminal = [row for row in history if row.ended_at is not None]
            if len(terminal) >= count:
                assert len(terminal) == count
                assert all(row.status.value == status for row in terminal)
                assert all(row.duration_ms is not None and row.duration_ms >= 0 for row in terminal)
                return terminal
            await asyncio.sleep(0.01)


def assert_next_calendar_day(job, weekday):
    from datetime import datetime

    reference = datetime(2026, 1, 4, tzinfo=job.trigger.timezone)
    next_run = job.trigger.get_next_fire_time(None, reference)
    assert next_run is not None and next_run.weekday() == weekday
