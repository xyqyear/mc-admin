"""
Test restart scheduler functionality.

This test verifies the RestartScheduler utility class functionality,
including backup task conflict detection and restart time scheduling.
"""

import tempfile
from datetime import time
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.cron.restart_scheduler import RestartScheduler
from app.models import Base

from .test_cron_manager import TestCronManager
from .test_cronjobs import SampleCronJobParams, test_cron_registry


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
    test_manager = TestCronManager()
    await test_manager.initialize()

    # Clean up any existing cron jobs to ensure test isolation
    from sqlalchemy import delete

    from app.db.database import get_async_session
    from app.models import CronJob

    async with get_async_session() as session:
        await session.execute(delete(CronJob))
        await session.commit()

    yield test_manager
    await test_manager.shutdown()


@pytest.fixture
def restart_scheduler(fresh_cron_manager):
    """Create RestartScheduler instance for testing."""
    return RestartScheduler(fresh_cron_manager, restart_start_time=time(6, 0))


# Register backup and restart_server test cron jobs
@test_cron_registry.register(
    schema_cls=SampleCronJobParams,
    identifier="backup",
    description="测试备份任务",
)
async def backup_cronjob(context):
    """Test backup cron job."""
    context.log("执行备份任务")


@test_cron_registry.register(
    schema_cls=SampleCronJobParams,
    identifier="restart_server",
    description="测试服务器重启任务",
)
async def restart_server_cronjob(context):
    """Test restart server cron job."""
    context.log("执行服务器重启任务")


class TestRestartScheduler:
    """Test RestartScheduler functionality."""

    async def test_parse_cron_minute_field_single_value(self, restart_scheduler):
        """Test parsing single minute value."""
        minutes = restart_scheduler._parse_cron_minute_field("30")
        assert minutes == {30}

    async def test_parse_cron_minute_field_list_values(self, restart_scheduler):
        """Test parsing comma-separated minute values."""
        minutes = restart_scheduler._parse_cron_minute_field("0,15,30,45")
        assert minutes == {0, 15, 30, 45}

    async def test_parse_cron_minute_field_range(self, restart_scheduler):
        """Test parsing minute range."""
        minutes = restart_scheduler._parse_cron_minute_field("10-20")
        assert minutes == {10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20}

    async def test_parse_cron_minute_field_step_values(self, restart_scheduler):
        """Test parsing step values."""
        # Every 5 minutes
        minutes = restart_scheduler._parse_cron_minute_field("*/5")
        expected = set(range(0, 60, 5))
        assert minutes == expected

        # Every 10 minutes from 0-30
        minutes = restart_scheduler._parse_cron_minute_field("0-30/10")
        assert minutes == {0, 10, 20, 30}

    async def test_parse_cron_minute_field_wildcard(self, restart_scheduler):
        """Test parsing wildcard."""
        minutes = restart_scheduler._parse_cron_minute_field("*")
        assert minutes == set(range(60))

    async def test_parse_cron_minute_field_complex(self, restart_scheduler):
        """Test parsing complex minute expressions."""
        # Mix of different patterns
        minutes = restart_scheduler._parse_cron_minute_field("0,15,30-35,*/20")
        expected = {0, 15, 30, 31, 32, 33, 34, 35, 20, 40}
        assert minutes == expected

    async def test_get_backup_minutes_empty(self, restart_scheduler):
        """Test getting backup minutes when no backup tasks exist."""
        backup_minutes = await restart_scheduler.get_backup_minutes()
        assert backup_minutes == set()

    async def test_get_backup_minutes_with_tasks(
        self, restart_scheduler, fresh_cron_manager
    ):
        """Test getting backup minutes with existing backup tasks."""
        # Create backup tasks with different schedules
        params = SampleCronJobParams(message="Test backup")

        # Backup task 1: "0,15 * * * *" - minutes 0, 15
        await fresh_cron_manager.create_cronjob(
            identifier="backup", params=params, cron="0,15 * * * *", name="Backup 1"
        )

        # Backup task 2: "30 1 * * *" - minute 30
        await fresh_cron_manager.create_cronjob(
            identifier="backup", params=params, cron="30 1 * * *", name="Backup 2"
        )

        backup_minutes = await restart_scheduler.get_backup_minutes()
        expected = {0, 15, 30}
        assert backup_minutes == expected

    async def test_get_restart_minutes(self, restart_scheduler, fresh_cron_manager):
        """Test getting restart minutes with existing restart tasks."""
        params = SampleCronJobParams(message="Test restart")

        # Restart task 1: "5 6 * * *" - minute 5
        await fresh_cron_manager.create_cronjob(
            identifier="restart_server",
            params=params,
            cron="5 6 * * *",
            name="Restart 1",
        )

        # Restart task 2: "25 8 * * *" - minute 25
        await fresh_cron_manager.create_cronjob(
            identifier="restart_server",
            params=params,
            cron="25 8 * * *",
            name="Restart 2",
        )

        restart_minutes = await restart_scheduler.get_restart_minutes()
        expected = {5, 25}
        assert restart_minutes == expected

    async def test_find_next_available_restart_time_no_conflicts(
        self, restart_scheduler
    ):
        """Test finding restart time when no backup tasks exist."""
        # Default start time is 6:00, and no conflicts exist
        hour, minute = await restart_scheduler.find_next_available_restart_time()
        assert hour == 6
        assert minute == 0  # Should be the start time since no conflicts

    async def test_find_next_available_restart_time_with_conflicts(
        self, restart_scheduler, fresh_cron_manager
    ):
        """Test finding restart time when conflicts exist."""
        params = SampleCronJobParams(message="Test backup")

        # Create backup tasks that conflict with early morning times
        # Conflict at 6:00 (minute 0)
        await fresh_cron_manager.create_cronjob(
            identifier="backup",
            params=params,
            cron="0 * * * *",
            name="Backup at minute 0",
        )

        # Conflict at 6:05 (minute 5)
        await fresh_cron_manager.create_cronjob(
            identifier="backup",
            params=params,
            cron="5 * * * *",
            name="Backup at minute 5",
        )

        # Conflict at 6:10 (minute 10)
        await fresh_cron_manager.create_cronjob(
            identifier="backup",
            params=params,
            cron="10 * * * *",
            name="Backup at minute 10",
        )

        hour, minute = await restart_scheduler.find_next_available_restart_time()
        # Should find next available slot at 6:15
        assert hour == 6
        assert minute == 15

    async def test_find_next_available_restart_time_many_conflicts(
        self, restart_scheduler, fresh_cron_manager
    ):
        """Test finding restart time when many conflicts exist."""
        params = SampleCronJobParams(message="Test backup")

        # Create backup tasks that occupy most 5-minute slots in hour 6
        conflict_minutes = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50]
        for minute in conflict_minutes:
            await fresh_cron_manager.create_cronjob(
                identifier="backup",
                params=params,
                cron=f"{minute} * * * *",
                name=f"Backup at minute {minute}",
            )

        hour, minute = await restart_scheduler.find_next_available_restart_time()
        # Should find the only available slot at 6:55
        assert hour == 6
        assert minute == 55

    async def test_find_next_available_restart_time_rollover_hour(
        self, restart_scheduler, fresh_cron_manager
    ):
        """Test finding restart time that rolls over to next hour."""
        params = SampleCronJobParams(message="Test backup")

        # Fill all 5-minute slots in hour 6 and hour 7 to force rollover
        for hour in [6, 7]:
            for minute in range(0, 60, 5):
                await fresh_cron_manager.create_cronjob(
                    identifier="backup",
                    params=params,
                    cron=f"{minute} {hour} * * *",  # Specific hour to avoid global conflicts
                    name=f"Backup at {hour}:{minute:02d}",
                )

        # Now create global conflicts for specific minutes to force search
        conflict_minutes = list(range(0, 60, 5))  # All 5-minute intervals
        for minute in conflict_minutes:
            await fresh_cron_manager.create_cronjob(
                identifier="backup",
                params=params,
                cron=f"{minute} * * * *",  # Global minute conflict
                name=f"Global backup at minute {minute}",
            )

        hour, minute = await restart_scheduler.find_next_available_restart_time()
        # Should fallback to original start time when no slots available
        assert hour == 6
        assert minute == 0

    async def test_generate_restart_cron_default_pattern(self, restart_scheduler):
        """Test generating restart cron with default patterns."""
        cron_expr = await restart_scheduler.generate_restart_cron()
        parts = cron_expr.split()
        assert len(parts) == 5

        # Should be in format: "minute hour * * *"
        minute, hour, day, month, weekday = parts
        assert hour == "6"  # Default start hour
        assert minute == "0"  # No conflicts, so should be start minute
        assert day == "*"
        assert month == "*"
        assert weekday == "*"

    async def test_generate_restart_cron_custom_patterns(self, restart_scheduler):
        """Test generating restart cron with custom patterns."""
        cron_expr = await restart_scheduler.generate_restart_cron(
            day_pattern="1", month_pattern="*/2", weekday_pattern="1-5"
        )
        parts = cron_expr.split()
        minute, hour, day, month, weekday = parts

        assert day == "1"
        assert month == "*/2"
        assert weekday == "1-5"

    async def test_check_time_conflict(self, restart_scheduler, fresh_cron_manager):
        """Test checking time conflicts."""
        params = SampleCronJobParams(message="Test backup")

        # Create backup task at minute 30
        await fresh_cron_manager.create_cronjob(
            identifier="backup",
            params=params,
            cron="30 * * * *",
            name="Backup at minute 30",
        )

        # Check conflicts
        assert await restart_scheduler.check_time_conflict(6, 30) is True  # Conflict
        assert (
            await restart_scheduler.check_time_conflict(6, 25) is False
        )  # No conflict

    async def test_get_conflict_summary(self, restart_scheduler, fresh_cron_manager):
        """Test getting conflict summary."""
        params = SampleCronJobParams(message="Test")

        # Create backup tasks
        await fresh_cron_manager.create_cronjob(
            identifier="backup",
            params=params,
            cron="0,15,30 * * * *",
            name="Multi-minute backup",
        )

        # Create restart task
        await fresh_cron_manager.create_cronjob(
            identifier="restart_server",
            params=params,
            cron="15 6 * * *",
            name="Restart task",
        )

        summary = await restart_scheduler.get_conflict_summary()

        assert set(summary["backup_minutes"]) == {0, 15, 30}
        assert set(summary["restart_minutes"]) == {15}
        assert set(summary["conflicts"]) == {15}  # Common minute
        assert 5 in summary["available_5min_slots"]  # 5 should be available
        assert 0 not in summary["available_5min_slots"]  # 0 should not be available
        assert 15 not in summary["available_5min_slots"]  # 15 should not be available
        assert 30 not in summary["available_5min_slots"]  # 30 should not be available
        assert summary["restart_start_time"] == "06:00"

    async def test_custom_restart_start_time(self, fresh_cron_manager):
        """Test RestartScheduler with custom start time."""
        # Create scheduler with different start time
        custom_scheduler = RestartScheduler(
            fresh_cron_manager, restart_start_time=time(8, 30)
        )

        hour, minute = await custom_scheduler.find_next_available_restart_time()
        assert hour == 8
        assert minute == 30  # Should start at 8:30

        # Test rounding down to current 5-minute interval
        custom_scheduler = RestartScheduler(
            fresh_cron_manager, restart_start_time=time(9, 23)
        )
        hour, minute = await custom_scheduler.find_next_available_restart_time()
        assert hour == 9
        assert minute == 20  # Should round down to current 5-minute interval (20)

    async def test_include_paused_jobs_in_conflicts(
        self, restart_scheduler, fresh_cron_manager
    ):
        """Test that paused backup jobs are still considered for conflicts."""
        params = SampleCronJobParams(message="Test backup")

        # Create backup task
        cronjob_id = await fresh_cron_manager.create_cronjob(
            identifier="backup", params=params, cron="0 * * * *", name="Paused backup"
        )

        # Pause the backup task
        await fresh_cron_manager.pause_cronjob(cronjob_id)

        # Paused jobs should still be considered for conflicts
        backup_minutes = await restart_scheduler.get_backup_minutes()
        assert 0 in backup_minutes

        # Should still detect conflict
        assert await restart_scheduler.check_time_conflict(6, 0) is True
