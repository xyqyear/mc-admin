"""
Test cron jobs for cron system testing.

These cron jobs are only used during testing and should not be available
in production environments.
"""

import asyncio
from typing import cast

from app.cron.registry import CronRegistry
from app.cron.types import ExecutionContext
from app.dynamic_config.schemas import BaseConfigSchema

# Create a test-specific cron registry
test_cron_registry = CronRegistry()


class SampleCronJobParams(BaseConfigSchema):
    """Parameters for sample cron job."""

    message: str = "Hello, World!"
    delay_seconds: int = 0


@test_cron_registry.register(
    schema_cls=SampleCronJobParams,
    identifier="test_cronjob",
    description="简单的测试定时任务",
)
async def sample_cronjob(context: ExecutionContext):
    """
    示例定时任务：测试定时任务

    这是一个简单的测试定时任务，用于验证定时任务系统的基本功能。
    """
    params: SampleCronJobParams = cast(SampleCronJobParams, context.params)

    context.log("测试定时任务开始执行")
    context.log(f"收到消息: {params.message}")

    if params.delay_seconds > 0:
        context.log(f"等待 {params.delay_seconds} 秒...")
        await asyncio.sleep(params.delay_seconds)

    context.log("测试定时任务执行完成")
