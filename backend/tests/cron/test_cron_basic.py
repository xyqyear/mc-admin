"""Basic cron scheduler tests: creation, execution, and lifecycle."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import get_async_session
from app.models import Base, CronJob, CronJobExecution, CronJobStatus, ExecutionStatus

from .test_cron_manager import test_cron_registry
from .test_cronjobs import SampleCronJobParams


@pytest.fixture(scope="module", autouse=True)
async def setup_test_db():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
        TEST_DB_PATH = tmp_file.name

    test_db_url = f"sqlite+aiosqlite:///{TEST_DB_PATH}"
    TEST_ENGINE = create_async_engine(test_db_url, echo=False)
    TEST_SESSION_MAKER = async_sessionmaker(
        bind=TEST_ENGINE,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    with (
        patch("app.db.database.AsyncSessionLocal", TEST_SESSION_MAKER),
        patch("app.db.database.engine", TEST_ENGINE),
        patch("app.cron.manager.get_async_session") as mock_get_session,
    ):
        def get_test_session():
            return TEST_SESSION_MAKER()

        mock_get_session.side_effect = get_test_session

        yield

    if TEST_ENGINE:
        await TEST_ENGINE.dispose()
    if TEST_DB_PATH and Path(TEST_DB_PATH).exists():
        Path(TEST_DB_PATH).unlink()


@pytest.fixture
async def fresh_cron_manager():
    from .test_cron_manager import TestCronManager

    test_manager = TestCronManager()
    await test_manager.initialize()
    yield test_manager
    await test_manager.shutdown()


class TestBasicCronJobFunctionality:
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

    async def test_cronjob_execution_with_second_star(self, fresh_cron_manager):
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Quick test", delay_seconds=0)

        cronjob_id = await cron_manager.create_cronjob(
            identifier="test_cronjob", params=params, cron="* * * * *", second="*"
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

            execution = executions[0]
            assert execution.cronjob_id == cronjob_id
            assert execution.status in [
                ExecutionStatus.COMPLETED,
                ExecutionStatus.RUNNING,
            ]
            assert execution.started_at is not None

            if execution.status == ExecutionStatus.COMPLETED:
                assert execution.ended_at is not None
                assert execution.duration_ms is not None
                assert execution.duration_ms >= 0

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

        with pytest.raises(ValueError, match="not registered"):
            await cron_manager.create_cronjob(
                identifier="nonexistent_cronjob", params=params, cron="0 * * * *"
            )

    async def test_cronjob_with_failure(self, fresh_cron_manager):
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Failure test", delay_seconds=-1)

        @test_cron_registry.register(
            schema_cls=SampleCronJobParams,
            identifier="failing_test_cronjob",
            description="CronJob that fails for testing",
        )
        async def failing_cronjob(context):
            if context.params.delay_seconds < 0:
                raise ValueError("Invalid delay seconds")
            await asyncio.sleep(context.params.delay_seconds)

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
