"""Sample cron jobs for cron system tests; not registered in production."""

import asyncio
from typing import cast

from app.cron.registry import CronRegistry
from app.cron.types import ExecutionContext
from app.dynamic_config.schemas import BaseConfigSchema

test_cron_registry = CronRegistry()


class SampleCronJobParams(BaseConfigSchema):
    message: str = "Hello, World!"
    delay_seconds: int = 0


@test_cron_registry.register(
    schema_cls=SampleCronJobParams,
    identifier="test_cronjob",
    description="Simple test cron job",
)
async def sample_cronjob(context: ExecutionContext):
    params: SampleCronJobParams = cast(SampleCronJobParams, context.params)

    context.log("Test cron job started")
    context.log(f"Received message: {params.message}")

    if params.delay_seconds > 0:
        context.log(f"Waiting {params.delay_seconds} seconds...")
        await asyncio.sleep(params.delay_seconds)

    context.log("Test cron job finished")
