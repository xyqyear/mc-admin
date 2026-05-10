"""Cron job persistence and recovery across simulated restarts."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import get_async_session
from app.models import Base, CronJob, CronJobExecution, CronJobStatus, ExecutionStatus

from .test_cron_manager import TestCronManager, test_cron_registry
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


class TestCronJobPersistence:
    async def test_cronjob_recovery_after_restart(self):
        manager1 = TestCronManager()
        await manager1.initialize()

        params1 = SampleCronJobParams(message="Recovery test 1", delay_seconds=0)
        params2 = SampleCronJobParams(message="Recovery test 2", delay_seconds=0)

        active_cronjob_id = await manager1.create_cronjob(
            identifier="test_cronjob",
            params=params1,
            cron="* * * * *",
            second="*",
            name="Active CronJob",
        )

        paused_cronjob_id = await manager1.create_cronjob(
            identifier="test_cronjob",
            params=params2,
            cron="* * * * *",
            name="Paused CronJob",
        )

        cancelled_cronjob_id = await manager1.create_cronjob(
            identifier="test_cronjob",
            params=params2,
            cron="0 0 * * *",
            name="Cancelled CronJob",
        )

        await manager1.pause_cronjob(paused_cronjob_id)
        await manager1.cancel_cronjob(cancelled_cronjob_id)

        assert manager1.scheduler.get_job(active_cronjob_id) is not None
        assert manager1.scheduler.get_job(paused_cronjob_id) is None
        assert manager1.scheduler.get_job(cancelled_cronjob_id) is None

        await manager1.shutdown()

        manager2 = TestCronManager()
        await manager2.initialize()

        assert manager2.scheduler.get_job(active_cronjob_id) is not None, (
            "Active cron job should be recovered after restart"
        )

        assert manager2.scheduler.get_job(paused_cronjob_id) is None, (
            "Paused cron job should not be recovered after restart"
        )

        assert manager2.scheduler.get_job(cancelled_cronjob_id) is None, (
            "Cancelled cron job should not be recovered after restart"
        )

        active_config = await manager2.get_cronjob_config(active_cronjob_id)
        assert active_config is not None
        assert active_config.identifier == "test_cronjob"
        assert active_config.name == "Active CronJob"
        assert active_config.status == CronJobStatus.ACTIVE
        assert isinstance(active_config.params, SampleCronJobParams)
        assert active_config.params.message == "Recovery test 1"

        paused_config = await manager2.get_cronjob_config(paused_cronjob_id)
        assert paused_config is not None
        assert paused_config.status == CronJobStatus.PAUSED

        cancelled_config = await manager2.get_cronjob_config(cancelled_cronjob_id)
        assert cancelled_config is not None
        assert cancelled_config.status == CronJobStatus.CANCELLED

        await manager2.shutdown()

    async def test_paused_cronjob_can_be_resumed_after_restart(self):
        manager1 = TestCronManager()
        await manager1.initialize()

        params = SampleCronJobParams(message="Resume after restart test")

        cronjob_id = await manager1.create_cronjob(
            identifier="test_cronjob",
            params=params,
            cron="* * * * *",
            second="*",
            name="Resume Test CronJob",
        )

        await manager1.pause_cronjob(cronjob_id)

        assert manager1.scheduler.get_job(cronjob_id) is None

        await manager1.shutdown()

        manager2 = TestCronManager()
        await manager2.initialize()

        assert manager2.scheduler.get_job(cronjob_id) is None

        await manager2.resume_cronjob(cronjob_id)

        assert manager2.scheduler.get_job(cronjob_id) is not None

        config = await manager2.get_cronjob_config(cronjob_id)
        assert config is not None
        assert config.status == CronJobStatus.ACTIVE

        await manager2.shutdown()

    async def test_duplicate_cronjob_id_recovery(self):
        manager = TestCronManager()
        await manager.initialize()

        original_params = SampleCronJobParams(
            message="Original cron job", delay_seconds=1
        )
        custom_cronjob_id = "duplicate_test_cronjob"

        returned_id = await manager.create_cronjob(
            identifier="test_cronjob",
            params=original_params,
            cron="0 0 * * *",
            cronjob_id=custom_cronjob_id,
            name="Original CronJob",
        )

        assert returned_id == custom_cronjob_id

        await manager.cancel_cronjob(custom_cronjob_id)

        config = await manager.get_cronjob_config(custom_cronjob_id)
        assert config is not None
        assert config.status == CronJobStatus.CANCELLED
        assert manager.scheduler.get_job(custom_cronjob_id) is None

        new_params = SampleCronJobParams(message="Recovered cron job", delay_seconds=2)

        recovered_id = await manager.create_cronjob(
            identifier="test_cronjob",
            params=new_params,
            cron="*/5 * * * *",
            cronjob_id=custom_cronjob_id,
            name="Recovered CronJob",
        )

        assert recovered_id == custom_cronjob_id

        config = await manager.get_cronjob_config(custom_cronjob_id)
        assert config is not None, "CronJob config should exist after recovery"
        assert config.status == CronJobStatus.ACTIVE
        assert config.name == "Recovered CronJob"
        assert config.cron == "*/5 * * * *"
        assert isinstance(config.params, SampleCronJobParams)
        assert config.params.message == "Recovered cron job"
        assert config.params.delay_seconds == 2

        assert manager.scheduler.get_job(custom_cronjob_id) is not None

        await manager.shutdown()

    async def test_execution_history_persistence(self):
        manager = TestCronManager()
        await manager.initialize()

        params = SampleCronJobParams(message="Execution history test", delay_seconds=0)

        cronjob_id = await manager.create_cronjob(
            identifier="test_cronjob",
            params=params,
            cron="* * * * *",
            second="*",
            name="History Test CronJob",
        )

        await asyncio.sleep(3)

        executions = await manager.get_execution_history(cronjob_id, limit=10)

        assert len(executions) >= 1, "Should have at least one execution"

        for execution in executions:
            assert execution.cronjob_id == cronjob_id
            assert execution.execution_id is not None
            assert execution.started_at is not None
            assert execution.status in [s for s in ExecutionStatus]
            assert isinstance(execution.messages, list)

            if execution.status == ExecutionStatus.COMPLETED:
                assert execution.ended_at is not None
                assert execution.duration_ms is not None
                assert execution.duration_ms >= 0

        async with get_async_session() as session:
            result = await session.execute(
                select(CronJobExecution).where(
                    CronJobExecution.cronjob_id == cronjob_id
                )
            )
            db_executions = result.scalars().all()

            assert len(db_executions) >= 1
            assert all(ex.cronjob_id == cronjob_id for ex in db_executions)

        await manager.shutdown()

    async def test_cronjob_parameter_serialization(self):
        manager = TestCronManager()
        await manager.initialize()

        params = SampleCronJobParams(
            message="Complex serialization test with unicode: 测试中文",
            delay_seconds=42,
        )

        cronjob_id = await manager.create_cronjob(
            identifier="test_cronjob",
            params=params,
            cron="0 0 * * *",
            name="Serialization Test",
        )

        async with get_async_session() as session:
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            db_cronjob = result.scalar_one()

            schema_cls = test_cron_registry.get_schema_class("test_cronjob")
            assert schema_cls is not None
            deserialized_params = schema_cls.model_validate_json(db_cronjob.params_json)
            assert isinstance(deserialized_params, SampleCronJobParams)

            assert (
                deserialized_params.message
                == "Complex serialization test with unicode: 测试中文"
            )
            assert deserialized_params.delay_seconds == 42

        config = await manager.get_cronjob_config(cronjob_id)
        assert config is not None
        assert isinstance(config.params, SampleCronJobParams)
        assert (
            config.params.message == "Complex serialization test with unicode: 测试中文"
        )
        assert config.params.delay_seconds == 42

        await manager.shutdown()

    async def test_execution_count_persistence(self):
        manager1 = TestCronManager()
        await manager1.initialize()

        params = SampleCronJobParams(message="Count persistence test", delay_seconds=0)

        cronjob_id = await manager1.create_cronjob(
            identifier="test_cronjob",
            params=params,
            cron="* * * * *",
            second="*",
            name="Count Test",
        )

        await asyncio.sleep(3)

        config1 = await manager1.get_cronjob_config(cronjob_id)
        assert config1 is not None
        initial_count = config1.execution_count

        assert initial_count >= 1, "Should have at least one execution"

        await manager1.shutdown()

        manager2 = TestCronManager()
        await manager2.initialize()

        await asyncio.sleep(2)

        config2 = await manager2.get_cronjob_config(cronjob_id)
        assert config2 is not None
        final_count = config2.execution_count

        assert final_count > initial_count, (
            f"Execution count should increase after restart: {initial_count} -> {final_count}"
        )

        await manager2.shutdown()
