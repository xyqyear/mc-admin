"""Cron expression validation and execution timing tests."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import get_async_session
from app.models import Base, CronJob, CronJobExecution, ExecutionStatus

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


class TestCronScheduling:
    async def test_cronjob_scheduled_to_run_in_5_seconds(self, fresh_cron_manager):
        cron_manager = fresh_cron_manager

        params = SampleCronJobParams(message="Cron timing test", delay_seconds=0)

        cronjob_id = await cron_manager.create_cronjob(
            identifier="test_cronjob",
            params=params,
            cron="* * * * *",
            second="*",
            name="Cron Timing Test CronJob",
        )

        scheduled_job = cron_manager.scheduler.get_job(cronjob_id)
        assert scheduled_job is not None, "CronJob should be scheduled"

        max_wait_time = 5
        execution_found = False

        for i in range(max_wait_time):
            await asyncio.sleep(1)

            async with get_async_session() as session:
                result = await session.execute(
                    select(CronJobExecution).where(
                        CronJobExecution.cronjob_id == cronjob_id
                    )
                )
                executions = result.scalars().all()

                if executions:
                    execution_found = True
                    execution = executions[0]

                    assert execution.cronjob_id == cronjob_id
                    assert execution.execution_id is not None
                    assert execution.started_at is not None

                    assert execution.status in [
                        ExecutionStatus.COMPLETED,
                        ExecutionStatus.RUNNING,
                    ]

                    if execution.status == ExecutionStatus.COMPLETED:
                        assert execution.ended_at is not None
                        assert execution.duration_ms is not None
                        assert execution.duration_ms >= 0

                        assert execution.duration_ms < 2000, (
                            "CronJob should complete quickly"
                        )

                    break

        assert execution_found, (
            f"CronJob did not execute within {max_wait_time} seconds."
        )

    async def test_cron_validation_with_different_expressions(self, fresh_cron_manager):
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Validation test")

        test_cases = [
            ("0 0 * * *", None, "Daily at midnight"),
            ("0 */2 * * *", None, "Every 2 hours"),
            ("30 9 * * 1-5", None, "9:30 AM on weekdays"),
            ("0 0 1 * *", None, "First day of every month"),
            ("* * * * *", "*", "Every second"),
            ("*/5 * * * *", None, "Every 5 minutes"),
        ]

        created_cronjobs = []

        for cron_expr, second, description in test_cases:
            cronjob_id = await cron_manager.create_cronjob(
                identifier="test_cronjob",
                params=params,
                cron=cron_expr,
                second=second,
                name=f"Cron Test: {description}",
            )

            created_cronjobs.append(cronjob_id)

            scheduled_job = cron_manager.scheduler.get_job(cronjob_id)
            assert scheduled_job is not None, (
                f"Cron expression '{cron_expr}' should be valid"
            )

            from apscheduler.triggers.cron import CronTrigger

            assert isinstance(scheduled_job.trigger, CronTrigger), (
                f"CronJob with cron '{cron_expr}' should have CronTrigger"
            )

        scheduled_job_ids = [job.id for job in cron_manager.scheduler.get_jobs()]
        for cronjob_id in created_cronjobs:
            assert cronjob_id in scheduled_job_ids, (
                f"CronJob {cronjob_id} should be scheduled"
            )

    async def test_invalid_cron_expressions(self, fresh_cron_manager):
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Invalid cron test")

        invalid_cron_expressions = [
            "invalid",
            "60 * * * *",  # minute > 59
            "* 25 * * *",  # hour > 23
            "* * 32 * *",  # day > 31
            "* * * 13 *",  # month > 12
            "* * * * 8",  # dow > 7
        ]

        for invalid_cron in invalid_cron_expressions:
            with pytest.raises(ValueError) as error:
                await cron_manager.create_cronjob(
                    identifier="test_cronjob",
                    params=params,
                    cron=invalid_cron,
                    name=f"Invalid Cron Test: {invalid_cron}",
                )

            error_msg = str(error.value).lower()
            assert any(
                keyword in error_msg
                for keyword in ["cron", "invalid", "error", "value", "expression"]
            ), f"Expected cron-related error for '{invalid_cron}', got: {error.value}"

    async def test_weekday_expression_is_preserved_and_update_is_atomic(
        self, fresh_cron_manager
    ):
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Weekday lifecycle test")

        cronjob_id = await cron_manager.create_cronjob(
            identifier="test_cronjob",
            params=params,
            cron="0 1 * * 1",
        )

        async with get_async_session() as session:
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            row = result.scalar_one()
            assert row.cron == "0 1 * * 1"

        scheduled_job = cron_manager.scheduler.get_job(cronjob_id)
        assert scheduled_job is not None
        assert str(scheduled_job.trigger.fields[4]) == "0"

        with pytest.raises(ValueError, match="星期字段"):
            await cron_manager.update_cronjob(
                cronjob_id=cronjob_id,
                identifier="test_cronjob",
                params=params,
                cron="0 1 * * 8",
            )

        async with get_async_session() as session:
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            row = result.scalar_one()
            assert row.cron == "0 1 * * 1"

        scheduled_job = cron_manager.scheduler.get_job(cronjob_id)
        assert scheduled_job is not None
        assert str(scheduled_job.trigger.fields[4]) == "0"

        await cron_manager.pause_cronjob(cronjob_id)
        await cron_manager.resume_cronjob(cronjob_id)

        scheduled_job = cron_manager.scheduler.get_job(cronjob_id)
        assert scheduled_job is not None
        assert str(scheduled_job.trigger.fields[4]) == "0"
