"""Basic cron scheduler tests: creation, execution, and lifecycle."""
import asyncio
import json
from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy import select

import app.cron.manager as manager_module
from app.cron.models import CronJob, CronJobExecution, CronJobStatus, ExecutionStatus
from app.cron.types import CronJobConfig, ExecutionContext
from app.db.database import get_async_session

from .test_cron_manager import TestCronManager, test_cron_registry
from .test_cronjobs import SampleCronJobParams

pytestmark = pytest.mark.usefixtures("setup_test_db")


class TestBasicCronJobFunctionality:
    async def test_repeated_manager_lifecycle_restores_global_registry(self):
        original_registry = manager_module.get_cron_registry()
        manager = TestCronManager()

        for _ in range(2):
            try:
                await manager.initialize()
                assert manager_module.get_cron_registry() is test_cron_registry
                assert manager.scheduler.running
            finally:
                await manager.shutdown()
            await asyncio.sleep(0)

            assert manager_module.get_cron_registry() is original_registry
            assert not manager.scheduler.running
            assert not manager._initialized

    def test_config_preserves_dynamic_parameter_instance(self):
        params = SampleCronJobParams(message="Typed configuration", delay_seconds=5)
        now = datetime.now(UTC)
        config = CronJobConfig(
            cronjob_id="typed-config",
            identifier="test_cronjob",
            name="Typed configuration",
            cron="0 0 * * *",
            params=params,
            created_at=now,
            updated_at=now,
        )

        assert config.params is params
        assert isinstance(config.params, SampleCronJobParams)
        assert config.params.message == "Typed configuration"
        assert config.params.delay_seconds == 5

    async def test_cronjob_registry_basics(self):
        assert test_cron_registry.is_registered("test_cronjob")

        cronjob_registration = test_cron_registry.get_cronjob("test_cronjob")
        assert cronjob_registration is not None

        assert cronjob_registration.description == "Simple test cron job"
        assert cronjob_registration.schema_cls == SampleCronJobParams

    async def test_create_and_execute_cronjob(self, fresh_cron_manager):
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Test execution", delay_seconds=0)

        cronjob_id = await cron_manager.create_cronjob(
            identifier="test_cronjob",
            params=params,
            cron="* * * * *",
            second="*",
        )

        assert cronjob_id is not None
        assert cronjob_id.startswith("test_cronjob_")

        async with get_async_session() as session:
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            db_cronjob = result.scalar_one()

            assert db_cronjob.cronjob_id == cronjob_id
            assert db_cronjob.identifier == "test_cronjob"
            assert db_cronjob.status == CronJobStatus.ACTIVE
            assert db_cronjob.cron == "* * * * *"
            assert db_cronjob.second == "*"

        scheduled_job = cron_manager.scheduler.get_job(cronjob_id)
        assert scheduled_job is not None
        assert scheduled_job.id == cronjob_id

    async def test_scheduler_dispatch_finishes_the_same_committed_execution(self, fresh_cron_manager, tmp_path):
        manager = fresh_cron_manager
        entered = asyncio.get_running_loop().create_future()
        release = asyncio.Event()
        marker = tmp_path / "scheduled-effect.txt"

        async def write_marker(context: ExecutionContext):
            async with get_async_session() as session:
                row = (await session.execute(select(CronJobExecution).where(CronJobExecution.execution_id == context.execution_id))).scalar_one()
                assert row.status is ExecutionStatus.RUNNING
                assert row.ended_at is None
            entered.set_result(context.execution_id)
            await release.wait()
            marker.write_text(cast(SampleCronJobParams, context.params).message)
            context.log("scheduled marker committed")

        test_cron_registry.register_func(write_marker, SampleCronJobParams, identifier="scheduled_marker")
        job_id = await manager.create_cronjob(
            identifier="scheduled_marker", params=SampleCronJobParams(message="actual scheduled bytes"),
            cron="* * * * *", second="*",
        )
        try:
            execution_id = await asyncio.wait_for(asyncio.shield(entered), 5)
            await manager.pause_cronjob(job_id)
            assert manager.scheduler.get_job(job_id) is None
            assert not marker.exists()
            async with get_async_session() as session:
                row = (await session.execute(select(CronJobExecution).where(CronJobExecution.execution_id == execution_id))).scalar_one()
                assert row.status is ExecutionStatus.RUNNING
                assert row.ended_at is None
            release.set()
            async with asyncio.timeout(5):
                while True:
                    async with get_async_session() as session:
                        row = (await session.execute(select(CronJobExecution).where(CronJobExecution.execution_id == execution_id))).scalar_one()
                        if row.status is ExecutionStatus.COMPLETED:
                            assert row.ended_at is not None
                            assert row.duration_ms is not None and row.duration_ms >= 0
                            assert any("scheduled marker committed" in message for message in json.loads(row.messages_json))
                            break
                        assert row.status is ExecutionStatus.RUNNING
                    await asyncio.sleep(0.01)
            async with get_async_session() as session:
                executions = (await session.execute(select(CronJobExecution).where(CronJobExecution.cronjob_id == job_id))).scalars().all()
                job = (await session.execute(select(CronJob).where(CronJob.cronjob_id == job_id))).scalar_one()
                assert [record.execution_id for record in executions] == [execution_id]
                assert job.execution_count == 1
                assert job.status is CronJobStatus.PAUSED
            assert marker.read_text() == "actual scheduled bytes"
        finally:
            release.set()
            await manager.shutdown()
            test_cron_registry._cronjobs.pop("scheduled_marker", None)

    async def test_pause_and_resume_cronjob(self, fresh_cron_manager):
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Pause test")

        cronjob_id = await cron_manager.create_cronjob(
            identifier="test_cronjob", params=params, cron="* * * * *", second="*"
        )

        assert cron_manager.scheduler.get_job(cronjob_id) is not None

        await cron_manager.pause_cronjob(cronjob_id)

        async with get_async_session() as session:
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            db_cronjob = result.scalar_one()
            assert db_cronjob.status == CronJobStatus.PAUSED

        assert cron_manager.scheduler.get_job(cronjob_id) is None

        await cron_manager.resume_cronjob(cronjob_id)

        async with get_async_session() as session:
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            db_cronjob = result.scalar_one()
            assert db_cronjob.status == CronJobStatus.ACTIVE

        assert cron_manager.scheduler.get_job(cronjob_id) is not None

    async def test_cancel_cronjob(self, fresh_cron_manager):
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Cancel test")

        cronjob_id = await cron_manager.create_cronjob(
            identifier="test_cronjob", params=params, cron="* * * * *"
        )

        await cron_manager.cancel_cronjob(cronjob_id)

        async with get_async_session() as session:
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            db_cronjob = result.scalar_one()
            assert db_cronjob.status == CronJobStatus.CANCELLED

        assert cron_manager.scheduler.get_job(cronjob_id) is None

    async def test_get_cronjob_config(self, fresh_cron_manager):
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Config test", delay_seconds=5)

        cronjob_id = await cron_manager.create_cronjob(
            identifier="test_cronjob",
            params=params,
            cron="0 0 * * *",
            name="Test Configuration CronJob",
        )

        config = await cron_manager.get_cronjob_config(cronjob_id)

        assert config is not None
        assert config.cronjob_id == cronjob_id
        assert config.identifier == "test_cronjob"
        assert config.name == "Test Configuration CronJob"
        assert config.cron == "0 0 * * *"
        assert config.status == CronJobStatus.ACTIVE
        assert isinstance(config.params, SampleCronJobParams)
        assert config.params.message == "Config test"
        assert config.params.delay_seconds == 5

    async def test_custom_cronjob_id(self, fresh_cron_manager):
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Custom ID test")
        custom_cronjob_id = "my_custom_cronjob_123"

        returned_cronjob_id = await cron_manager.create_cronjob(
            identifier="test_cronjob",
            params=params,
            cron="0 * * * *",
            cronjob_id=custom_cronjob_id,
        )

        assert returned_cronjob_id == custom_cronjob_id

        async with get_async_session() as session:
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == custom_cronjob_id)
            )
            db_cronjob = result.scalar_one()
            assert db_cronjob.cronjob_id == custom_cronjob_id

    async def test_cronjob_execution_count_increment(self, fresh_cron_manager):
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Count test", delay_seconds=0)

        cronjob_id = await cron_manager.create_cronjob(
            identifier="test_cronjob", params=params, cron="* * * * *", second="*"
        )

        await asyncio.sleep(2)

        config = await cron_manager.get_cronjob_config(cronjob_id)
        assert config.execution_count >= 1

    async def test_invalid_cronjob_identifier(self, fresh_cron_manager):
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Invalid test")

        with pytest.raises(ValueError, match="未注册"):
            await cron_manager.create_cronjob(
                identifier="nonexistent_cronjob", params=params, cron="0 * * * *"
            )

    async def test_cronjob_with_failure(self, fresh_cron_manager):
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Failure test", delay_seconds=-1)

        async def failing_cronjob(context):
            if context.params.delay_seconds < 0:
                raise ValueError("Invalid delay seconds")
            await asyncio.sleep(context.params.delay_seconds)

        test_cron_registry.register_func(func=failing_cronjob, schema_cls=SampleCronJobParams, identifier="failing_test_cronjob", description="CronJob that fails for testing")

        cronjob_id = await cron_manager.create_cronjob(
            identifier="failing_test_cronjob",
            params=params,
            cron="* * * * *",
            second="*",
        )

        await asyncio.sleep(2)

        async with get_async_session() as session:
            result = await session.execute(
                select(CronJobExecution).where(
                    CronJobExecution.cronjob_id == cronjob_id
                )
            )
            executions = result.scalars().all()

            assert len(executions) >= 1
            failed_executions = [
                ex for ex in executions if ex.status == ExecutionStatus.FAILED
            ]
            assert len(failed_executions) >= 1
