"""
Test basic cron scheduler functionality.

This test verifies the core functionality of the cron job management system,
including cron job creation, execution, and lifecycle management.
"""

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


class TestBasicCronJobFunctionality:
    """Test basic cron job functionality."""

    async def test_cronjob_registry_basics(self):
        """Test that example cron jobs are registered correctly."""
        # Check that test cron job is registered
        assert test_cron_registry.is_registered("test_cronjob")

        # Get cron job information
        cronjob_registration = test_cron_registry.get_cronjob("test_cronjob")
        assert cronjob_registration is not None

        assert cronjob_registration.description == "简单的测试定时任务"
        assert cronjob_registration.schema_cls == SampleCronJobParams

    async def test_create_and_execute_cronjob(self, fresh_cron_manager):
        """Test creating and executing a cron job with second='*'."""
        cron_manager = fresh_cron_manager
        # Create cron job parameters
        params = SampleCronJobParams(message="Test execution", delay_seconds=0)

        # Create cron job that runs every second
        cronjob_id = await cron_manager.create_cronjob(
            identifier="test_cronjob",
            params=params,
            cron="* * * * *",  # Every minute (APScheduler format)
            second="*",  # Every second
        )

        assert cronjob_id is not None
        assert cronjob_id.startswith("test_cronjob_")

        # Verify cron job is in database
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

        # Verify cron job is scheduled in APScheduler
        scheduled_job = cron_manager.scheduler.get_job(cronjob_id)
        assert scheduled_job is not None
        assert scheduled_job.id == cronjob_id

    async def test_cronjob_execution_with_second_star(self, fresh_cron_manager):
        """Test that cron job actually executes when second='*'."""
        cron_manager = fresh_cron_manager
        # Create cron job parameters
        params = SampleCronJobParams(message="Quick test", delay_seconds=0)

        # Create cron job that runs every second
        cronjob_id = await cron_manager.create_cronjob(
            identifier="test_cronjob", params=params, cron="* * * * *", second="*"
        )

        # Wait for at least one execution (give it 2 seconds to be safe)
        await asyncio.sleep(2)

        # Check if execution record was created
        async with get_async_session() as session:
            result = await session.execute(
                select(CronJobExecution).where(
                    CronJobExecution.cronjob_id == cronjob_id
                )
            )
            executions = result.scalars().all()

            # Should have at least one execution
            assert len(executions) >= 1

            # Check the execution record
            execution = executions[0]
            assert execution.cronjob_id == cronjob_id
            assert execution.status in [
                ExecutionStatus.COMPLETED,
                ExecutionStatus.RUNNING,
            ]
            assert execution.started_at is not None

            # If completed, should have ended_at and duration
            if execution.status == ExecutionStatus.COMPLETED:
                assert execution.ended_at is not None
                assert execution.duration_ms is not None
                assert execution.duration_ms >= 0

    async def test_pause_and_resume_cronjob(self, fresh_cron_manager):
        """Test pausing and resuming a cron job."""
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Pause test")

        # Create cron job
        cronjob_id = await cron_manager.create_cronjob(
            identifier="test_cronjob", params=params, cron="* * * * *", second="*"
        )

        # Verify cron job is running
        assert cron_manager.scheduler.get_job(cronjob_id) is not None

        # Pause cron job
        await cron_manager.pause_cronjob(cronjob_id)

        # Verify cron job is paused in database
        async with get_async_session() as session:
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            db_cronjob = result.scalar_one()
            assert db_cronjob.status == CronJobStatus.PAUSED

        # Verify cron job is removed from scheduler
        assert cron_manager.scheduler.get_job(cronjob_id) is None

        # Resume cron job
        await cron_manager.resume_cronjob(cronjob_id)

        # Verify cron job is active again
        async with get_async_session() as session:
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            db_cronjob = result.scalar_one()
            assert db_cronjob.status == CronJobStatus.ACTIVE

        # Verify cron job is back in scheduler
        assert cron_manager.scheduler.get_job(cronjob_id) is not None

    async def test_cancel_cronjob(self, fresh_cron_manager):
        """Test canceling a cron job."""
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Cancel test")

        # Create cron job
        cronjob_id = await cron_manager.create_cronjob(
            identifier="test_cronjob", params=params, cron="* * * * *"
        )

        # Cancel cron job
        await cron_manager.cancel_cronjob(cronjob_id)

        # Verify cron job is cancelled in database
        async with get_async_session() as session:
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            db_cronjob = result.scalar_one()
            assert db_cronjob.status == CronJobStatus.CANCELLED

        # Verify cron job is removed from scheduler
        assert cron_manager.scheduler.get_job(cronjob_id) is None

    async def test_get_cronjob_config(self, fresh_cron_manager):
        """Test getting cron job configuration."""
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Config test", delay_seconds=5)

        # Create cron job
        cronjob_id = await cron_manager.create_cronjob(
            identifier="test_cronjob",
            params=params,
            cron="0 0 * * *",  # Daily at midnight
            name="Test Configuration CronJob",
        )

        # Get cron job config
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
        """Test creating cron job with custom cronjob_id."""
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Custom ID test")
        custom_cronjob_id = "my_custom_cronjob_123"

        # Create cron job with custom ID
        returned_cronjob_id = await cron_manager.create_cronjob(
            identifier="test_cronjob",
            params=params,
            cron="0 * * * *",
            cronjob_id=custom_cronjob_id,
        )

        assert returned_cronjob_id == custom_cronjob_id

        # Verify in database
        async with get_async_session() as session:
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == custom_cronjob_id)
            )
            db_cronjob = result.scalar_one()
            assert db_cronjob.cronjob_id == custom_cronjob_id

    async def test_cronjob_execution_count_increment(self, fresh_cron_manager):
        """Test that execution count is incremented after cron job runs."""
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Count test", delay_seconds=0)

        # Create cron job
        cronjob_id = await cron_manager.create_cronjob(
            identifier="test_cronjob", params=params, cron="* * * * *", second="*"
        )

        # Wait for execution
        await asyncio.sleep(2)

        # Check execution count
        config = await cron_manager.get_cronjob_config(cronjob_id)
        assert config.execution_count >= 1

    async def test_invalid_cronjob_identifier(self, fresh_cron_manager):
        """Test error handling for invalid cron job identifier."""
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Invalid test")

        # Try to create cron job with non-existent identifier
        with pytest.raises(ValueError, match="not registered"):
            await cron_manager.create_cronjob(
                identifier="nonexistent_cronjob", params=params, cron="0 * * * *"
            )

    async def test_cronjob_with_failure(self, fresh_cron_manager):
        """Test cron job execution that raises an exception."""
        cron_manager = fresh_cron_manager
        # We'll create a test cron job that fails by passing invalid delay
        params = SampleCronJobParams(
            message="Failure test", delay_seconds=-1
        )  # Invalid delay

        # Register a cron job that will fail
        @test_cron_registry.register(
            schema_cls=SampleCronJobParams,
            identifier="failing_test_cronjob",
            description="CronJob that fails for testing",
        )
        async def failing_cronjob(context):
            if context.params.delay_seconds < 0:
                raise ValueError("Invalid delay seconds")
            await asyncio.sleep(context.params.delay_seconds)

        # Create and run the failing cron job
        cronjob_id = await cron_manager.create_cronjob(
            identifier="failing_test_cronjob",
            params=params,
            cron="* * * * *",
            second="*",
        )

        # Wait for execution
        await asyncio.sleep(2)

        # Check execution record shows failure
        async with get_async_session() as session:
            result = await session.execute(
                select(CronJobExecution).where(
                    CronJobExecution.cronjob_id == cronjob_id
                )
            )
            executions = result.scalars().all()

            assert len(executions) >= 1
            # At least one execution should be failed
            failed_executions = [
                ex for ex in executions if ex.status == ExecutionStatus.FAILED
            ]
            assert len(failed_executions) >= 1
