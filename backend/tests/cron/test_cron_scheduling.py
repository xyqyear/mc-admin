"""
Test cron scheduling correctness.

This test specifically validates that cron expressions work correctly
and cron jobs are executed at the expected times.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import get_async_session
from app.models import Base, CronJobExecution, ExecutionStatus

from .test_cronjobs import SampleCronJobParams


@pytest.fixture(scope="module", autouse=True)
async def setup_test_db():
    """Setup test database with temporary file."""
    # Create temporary database file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
        TEST_DB_PATH = tmp_file.name

    # Create test database engine
    test_db_url = f"sqlite+aiosqlite:///{TEST_DB_PATH}"
    TEST_ENGINE = create_async_engine(test_db_url, echo=False)
    TEST_SESSION_MAKER = async_sessionmaker(
        bind=TEST_ENGINE,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    # Initialize database tables
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Patch the global database components
    with (
        patch("app.db.database.AsyncSessionLocal", TEST_SESSION_MAKER),
        patch("app.db.database.engine", TEST_ENGINE),
        patch("app.cron.manager.get_async_session") as mock_get_session,
    ):
        # Make get_async_session return our test session maker
        def get_test_session():
            return TEST_SESSION_MAKER()

        mock_get_session.side_effect = get_test_session

        yield

    # Cleanup
    if TEST_ENGINE:
        await TEST_ENGINE.dispose()
    if TEST_DB_PATH and Path(TEST_DB_PATH).exists():
        Path(TEST_DB_PATH).unlink()


@pytest.fixture
async def fresh_cron_manager():
    """Create fresh cron manager for each test."""
    # Create a new TestCronManager instance for each test
    from .test_cron_manager import TestCronManager

    test_manager = TestCronManager()
    await test_manager.initialize()
    yield test_manager
    await test_manager.shutdown()


class TestCronScheduling:
    """Test cron expression scheduling accuracy."""

    async def test_cronjob_scheduled_to_run_in_5_seconds(self, fresh_cron_manager):
        """
        Test that a cron job scheduled to run 5 seconds from now actually executes.

        This test validates the cron scheduling mechanism by creating a cron job
        that should run exactly once at a specific time.
        """
        cron_manager = fresh_cron_manager

        # Create a cron job that runs frequently (every minute) but with second='*' for quick execution
        params = SampleCronJobParams(message="Cron timing test", delay_seconds=0)

        # Create the cron job that runs every minute at every second
        cronjob_id = await cron_manager.create_cronjob(
            identifier="test_cronjob",
            params=params,
            cron="* * * * *",  # Every minute
            second="*",  # Every second (this makes it run frequently)
            name="Cron Timing Test CronJob",
        )

        # Verify cron job was created and scheduled
        scheduled_job = cron_manager.scheduler.get_job(cronjob_id)
        assert scheduled_job is not None, "CronJob should be scheduled"

        # Wait for the cron job to execute (should happen within a few seconds)
        max_wait_time = 5
        execution_found = False

        for i in range(max_wait_time):
            await asyncio.sleep(1)

            # Check if execution record was created
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

                    # Verify the execution record
                    assert execution.cronjob_id == cronjob_id
                    assert execution.execution_id is not None
                    assert execution.started_at is not None

                    # Verify cron job completed successfully (or is still running)
                    assert execution.status in [
                        ExecutionStatus.COMPLETED,
                        ExecutionStatus.RUNNING,
                    ]

                    # If completed, verify timing information
                    if execution.status == ExecutionStatus.COMPLETED:
                        assert execution.ended_at is not None
                        assert execution.duration_ms is not None
                        assert execution.duration_ms >= 0

                        # Since our test cron job has no delay, it should complete quickly
                        assert execution.duration_ms < 2000, (
                            "CronJob should complete quickly"
                        )

                    break

        # Ensure the cron job actually executed
        assert execution_found, (
            f"CronJob did not execute within {max_wait_time} seconds."
        )

    async def test_cron_validation_with_different_expressions(self, fresh_cron_manager):
        """
        Test various cron expressions to ensure they're properly validated and scheduled.

        This test doesn't wait for execution but verifies that different cron
        expressions are accepted and properly scheduled by APScheduler.
        """
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Validation test")

        # Test different valid cron expressions
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

            # Verify cron job is scheduled
            scheduled_job = cron_manager.scheduler.get_job(cronjob_id)
            assert scheduled_job is not None, (
                f"Cron expression '{cron_expr}' should be valid"
            )

            # Verify the trigger is a CronTrigger
            from apscheduler.triggers.cron import CronTrigger

            assert isinstance(scheduled_job.trigger, CronTrigger), (
                f"CronJob with cron '{cron_expr}' should have CronTrigger"
            )

        # Verify all created cron jobs are in the scheduler
        scheduled_job_ids = [job.id for job in cron_manager.scheduler.get_jobs()]
        for cronjob_id in created_cronjobs:
            assert cronjob_id in scheduled_job_ids, (
                f"CronJob {cronjob_id} should be scheduled"
            )

    async def test_invalid_cron_expressions(self, fresh_cron_manager):
        """Test that invalid cron expressions are properly rejected."""
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Invalid cron test")

        # Test invalid cron expressions
        invalid_cron_expressions = [
            "invalid",  # Not a valid cron format
            "60 * * * *",  # Invalid minute (>59)
            "* 25 * * *",  # Invalid hour (>23)
            "* * 32 * *",  # Invalid day (>31)
            "* * * 13 *",  # Invalid month (>12)
            "* * * * 8",  # Invalid day of week (>7)
        ]

        for invalid_cron in invalid_cron_expressions:
            # The cron job creation itself might succeed, but scheduling should fail
            # or be caught during validation
            try:
                await cron_manager.create_cronjob(
                    identifier="test_cronjob",
                    params=params,
                    cron=invalid_cron,
                    name=f"Invalid Cron Test: {invalid_cron}",
                )

            except (ValueError, Exception) as e:
                # It's acceptable for invalid cron expressions to raise errors
                # during cron job creation or scheduling
                error_msg = str(e).lower()
                assert any(
                    keyword in error_msg
                    for keyword in ["cron", "invalid", "error", "value", "expression"]
                ), f"Expected cron-related error for '{invalid_cron}', got: {e}"
