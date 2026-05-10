"""RestartScheduler tests: cron parsing, conflict detection, slot search."""

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
    test_manager = TestCronManager()
    await test_manager.initialize()

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
    return RestartScheduler(fresh_cron_manager, restart_start_time=time(6, 0))


@test_cron_registry.register(
    schema_cls=SampleCronJobParams,
    identifier="backup",
    description="测试备份任务",
)
async def backup_cronjob(context):
    context.log("Running backup task")


@test_cron_registry.register(
    schema_cls=SampleCronJobParams,
    identifier="restart_server",
    description="测试服务器重启任务",
)
async def restart_server_cronjob(context):
    context.log("Running server restart task")


class TestRestartScheduler:
    async def test_parse_cron_minute_field_single_value(self, restart_scheduler):
        minutes = restart_scheduler._parse_cron_minute_field("30")
        assert minutes == {30}

    async def test_parse_cron_minute_field_list_values(self, restart_scheduler):
        minutes = restart_scheduler._parse_cron_minute_field("0,15,30,45")
        assert minutes == {0, 15, 30, 45}

    async def test_parse_cron_minute_field_range(self, restart_scheduler):
        minutes = restart_scheduler._parse_cron_minute_field("10-20")
        assert minutes == {10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20}

    async def test_parse_cron_minute_field_step_values(self, restart_scheduler):
        minutes = restart_scheduler._parse_cron_minute_field("*/5")
        expected = set(range(0, 60, 5))
        assert minutes == expected

        minutes = restart_scheduler._parse_cron_minute_field("0-30/10")
        assert minutes == {0, 10, 20, 30}

    async def test_parse_cron_minute_field_wildcard(self, restart_scheduler):
        minutes = restart_scheduler._parse_cron_minute_field("*")
        assert minutes == set(range(60))

    async def test_parse_cron_minute_field_complex(self, restart_scheduler):
        minutes = restart_scheduler._parse_cron_minute_field("0,15,30-35,*/20")
        expected = {0, 15, 30, 31, 32, 33, 34, 35, 20, 40}
        assert minutes == expected

    async def test_parse_cron_hour_field_single_value(self, restart_scheduler):
        hours = restart_scheduler._parse_cron_hour_field("6")
        assert hours == {6}

    async def test_parse_cron_hour_field_list_values(self, restart_scheduler):
        hours = restart_scheduler._parse_cron_hour_field("6,8,12")
        assert hours == {6, 8, 12}

    async def test_parse_cron_hour_field_range(self, restart_scheduler):
        hours = restart_scheduler._parse_cron_hour_field("6-8")
        assert hours == {6, 7, 8}

    async def test_parse_cron_hour_field_step_values(self, restart_scheduler):
        hours = restart_scheduler._parse_cron_hour_field("*/6")
        expected = set(range(0, 24, 6))
        assert hours == expected

        hours = restart_scheduler._parse_cron_hour_field("6-18/2")
        assert hours == {6, 8, 10, 12, 14, 16, 18}

    async def test_parse_cron_hour_field_wildcard(self, restart_scheduler):
        hours = restart_scheduler._parse_cron_hour_field("*")
        assert hours == set(range(24))

    async def test_get_backup_minutes_empty(self, restart_scheduler):
        backup_minutes = await restart_scheduler.get_backup_minutes()
        assert backup_minutes == set()

    async def test_get_backup_minutes_with_tasks(
        self, restart_scheduler, fresh_cron_manager
    ):
        params = SampleCronJobParams(message="Test backup")

        await fresh_cron_manager.create_cronjob(
            identifier="backup", params=params, cron="0,15 * * * *", name="Backup 1"
        )

        await fresh_cron_manager.create_cronjob(
            identifier="backup", params=params, cron="30 1 * * *", name="Backup 2"
        )

        backup_minutes = await restart_scheduler.get_backup_minutes()
        expected = {0, 15, 30}
        assert backup_minutes == expected

    async def test_get_restart_time_slots(self, restart_scheduler, fresh_cron_manager):
        params = SampleCronJobParams(message="Test restart")

        await fresh_cron_manager.create_cronjob(
            identifier="restart_server",
            params=params,
            cron="5 6 * * *",
            name="restart-server1",
        )

        await fresh_cron_manager.create_cronjob(
            identifier="restart_server",
            params=params,
            cron="25 8 * * *",
            name="restart-server2",
        )

        restart_time_slots = await restart_scheduler.get_restart_time_slots()
        expected = {(6, 5), (8, 25)}
        assert restart_time_slots == expected

    async def test_get_restart_time_slots_with_exclusion(
        self, restart_scheduler, fresh_cron_manager
    ):
        params = SampleCronJobParams(message="Test restart")

        await fresh_cron_manager.create_cronjob(
            identifier="restart_server",
            params=params,
            cron="5 6 * * *",
            name="restart-server1",
        )

        await fresh_cron_manager.create_cronjob(
            identifier="restart_server",
            params=params,
            cron="25 8 * * *",
            name="restart-server2",
        )

        restart_time_slots = await restart_scheduler.get_restart_time_slots()
        assert restart_time_slots == {(6, 5), (8, 25)}

        restart_time_slots = await restart_scheduler.get_restart_time_slots(
            exclude_server_id="server1"
        )
        assert restart_time_slots == {(8, 25)}

    async def test_find_next_available_restart_time_no_conflicts(
        self, restart_scheduler
    ):
        hour, minute = await restart_scheduler.find_next_available_restart_time()
        assert hour == 6
        assert minute == 0

    async def test_find_next_available_restart_time_only_backup_conflicts(
        self, restart_scheduler, fresh_cron_manager
    ):
        params = SampleCronJobParams(message="Test backup")

        await fresh_cron_manager.create_cronjob(
            identifier="backup",
            params=params,
            cron="0 * * * *",
            name="Backup at minute 0",
        )

        hour, minute = await restart_scheduler.find_next_available_restart_time()
        assert hour == 6
        assert minute == 5

    async def test_find_next_available_restart_time_with_backup_and_restart_conflicts(
        self, restart_scheduler, fresh_cron_manager
    ):
        params = SampleCronJobParams(message="Test")

        await fresh_cron_manager.create_cronjob(
            identifier="backup",
            params=params,
            cron="0 * * * *",
            name="Backup at minute 0",
        )

        await fresh_cron_manager.create_cronjob(
            identifier="restart_server",
            params=params,
            cron="5 6 * * *",
            name="restart-other-server",
        )

        hour, minute = await restart_scheduler.find_next_available_restart_time()
        assert hour == 6
        assert minute == 10

    async def test_find_next_available_restart_time_with_exclusion(
        self, restart_scheduler, fresh_cron_manager
    ):
        params = SampleCronJobParams(message="Test")

        await fresh_cron_manager.create_cronjob(
            identifier="restart_server",
            params=params,
            cron="5 6 * * *",
            name="restart-current-server",
        )

        await fresh_cron_manager.create_cronjob(
            identifier="restart_server",
            params=params,
            cron="10 6 * * *",
            name="restart-other-server",
        )

        hour, minute = await restart_scheduler.find_next_available_restart_time()
        assert hour == 6
        assert minute == 0

        hour, minute = await restart_scheduler.find_next_available_restart_time(
            exclude_server_id="current-server"
        )
        assert hour == 6
        assert minute == 0

    async def test_find_next_available_restart_time_hour_6_full_restart_slots(
        self, restart_scheduler, fresh_cron_manager
    ):
        params = SampleCronJobParams(message="Test restart")

        for minute in range(0, 60, 5):
            await fresh_cron_manager.create_cronjob(
                identifier="restart_server",
                params=params,
                cron=f"{minute} 6 * * *",
                name=f"restart-server-{minute}",
            )

        hour, minute = await restart_scheduler.find_next_available_restart_time()
        assert hour == 7
        assert minute == 0

    async def test_find_next_available_restart_time_hour_6_full_with_backup_conflicts(
        self, restart_scheduler, fresh_cron_manager
    ):
        params = SampleCronJobParams(message="Test")

        await fresh_cron_manager.create_cronjob(
            identifier="backup",
            params=params,
            cron="0,5 * * * *",
            name="Backup at minutes 0 and 5",
        )

        for minute in range(0, 60, 5):
            await fresh_cron_manager.create_cronjob(
                identifier="restart_server",
                params=params,
                cron=f"{minute} 6 * * *",
                name=f"restart-server-{minute}",
            )

        hour, minute = await restart_scheduler.find_next_available_restart_time()
        assert hour == 7
        assert minute == 10

    async def test_find_next_available_restart_time_many_conflicts(
        self, restart_scheduler, fresh_cron_manager
    ):
        params = SampleCronJobParams(message="Test backup")

        conflict_minutes = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50]
        for minute in conflict_minutes:
            await fresh_cron_manager.create_cronjob(
                identifier="backup",
                params=params,
                cron=f"{minute} * * * *",
                name=f"Backup at minute {minute}",
            )

        hour, minute = await restart_scheduler.find_next_available_restart_time()
        assert hour == 6
        assert minute == 55

    async def test_find_next_available_restart_time_rollover_hour(
        self, restart_scheduler, fresh_cron_manager
    ):
        params = SampleCronJobParams(message="Test backup")

        for hour in [6, 7]:
            for minute in range(0, 60, 5):
                await fresh_cron_manager.create_cronjob(
                    identifier="backup",
                    params=params,
                    cron=f"{minute} {hour} * * *",
                    name=f"Backup at {hour}:{minute:02d}",
                )

        conflict_minutes = list(range(0, 60, 5))
        for minute in conflict_minutes:
            await fresh_cron_manager.create_cronjob(
                identifier="backup",
                params=params,
                cron=f"{minute} * * * *",
                name=f"Global backup at minute {minute}",
            )

        hour, minute = await restart_scheduler.find_next_available_restart_time()
        # Falls back to start time when nothing fits.
        assert hour == 6
        assert minute == 0

    async def test_generate_restart_cron_default_pattern(self, restart_scheduler):
        cron_expr = await restart_scheduler.generate_restart_cron()
        parts = cron_expr.split()
        assert len(parts) == 5

        minute, hour, day, month, weekday = parts
        assert hour == "6"
        assert minute == "0"
        assert day == "*"
        assert month == "*"
        assert weekday == "*"

    async def test_generate_restart_cron_custom_patterns(self, restart_scheduler):
        cron_expr = await restart_scheduler.generate_restart_cron(
            day_pattern="1", month_pattern="*/2", weekday_pattern="1-5"
        )
        parts = cron_expr.split()
        minute, hour, day, month, weekday = parts

        assert day == "1"
        assert month == "*/2"
        assert weekday == "1-5"

    async def test_check_time_conflict(self, restart_scheduler, fresh_cron_manager):
        params = SampleCronJobParams(message="Test")

        await fresh_cron_manager.create_cronjob(
            identifier="backup",
            params=params,
            cron="30 * * * *",
            name="Backup at minute 30",
        )

        await fresh_cron_manager.create_cronjob(
            identifier="restart_server",
            params=params,
            cron="25 6 * * *",
            name="restart-server1",
        )

        assert await restart_scheduler.check_time_conflict(6, 30) is True
        assert await restart_scheduler.check_time_conflict(6, 25) is True
        assert await restart_scheduler.check_time_conflict(8, 25) is False
        assert await restart_scheduler.check_time_conflict(6, 20) is False

        assert (
            await restart_scheduler.check_time_conflict(
                6, 25, exclude_server_id="server1"
            )
            is False
        )

    async def test_custom_restart_start_time(self, fresh_cron_manager):
        custom_scheduler = RestartScheduler(
            fresh_cron_manager, restart_start_time=time(8, 30)
        )

        hour, minute = await custom_scheduler.find_next_available_restart_time()
        assert hour == 8
        assert minute == 30

        # Rounds down to current 5-minute interval.
        custom_scheduler = RestartScheduler(
            fresh_cron_manager, restart_start_time=time(9, 23)
        )
        hour, minute = await custom_scheduler.find_next_available_restart_time()
        assert hour == 9
        assert minute == 20

    async def test_include_paused_jobs_in_conflicts(
        self, restart_scheduler, fresh_cron_manager
    ):
        """Paused backup jobs still count toward conflicts."""
        params = SampleCronJobParams(message="Test backup")

        cronjob_id = await fresh_cron_manager.create_cronjob(
            identifier="backup", params=params, cron="0 * * * *", name="Paused backup"
        )

        await fresh_cron_manager.pause_cronjob(cronjob_id)

        backup_minutes = await restart_scheduler.get_backup_minutes()
        assert 0 in backup_minutes

        assert await restart_scheduler.check_time_conflict(6, 0) is True
