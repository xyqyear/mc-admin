import tempfile
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.cron import crud
from app.cron.manager import CronManager
from app.cron.registry import CronRegistry, cron_registry
from app.dynamic_config.schemas import BaseConfigSchema
from app.models import Base, CronJobStatus


class SystemCronParams(BaseConfigSchema):
    value: str = "default"


async def system_test_job(context) -> None:
    context.log("system test job")


def test_self_check_system_cron_defaults_to_hourly() -> None:
    registration = cron_registry.get_cronjob("self_check")

    assert registration is not None
    assert registration.is_system is True
    assert registration.default_cron == "0 * * * *"
    assert registration.default_second == "0"


@pytest.fixture
async def cron_test_db(monkeypatch: pytest.MonkeyPatch):
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()

    engine = create_async_engine(f"sqlite+aiosqlite:///{temp_db.name}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    import app.cron.manager as manager_module

    monkeypatch.setattr(manager_module, "get_async_session", session_factory)
    yield session_factory

    await engine.dispose()
    Path(temp_db.name).unlink(missing_ok=True)


async def test_system_cronjob_created_and_protected(
    cron_test_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = CronRegistry()
    registry.register_func(
        func=system_test_job,
        schema_cls=SystemCronParams,
        identifier="system_test",
        description="System test job",
        is_system=True,
        default_cron="0 5 * * *",
        default_second="0",
        default_params=SystemCronParams(value="default"),
        default_name="System Test",
    )
    registry.register_func(
        func=system_test_job,
        schema_cls=SystemCronParams,
        identifier="other_test",
        description="Other test job",
    )

    import app.cron.manager as manager_module

    monkeypatch.setattr(manager_module, "cron_registry", registry)

    manager = CronManager()
    await manager.initialize()
    try:
        cronjob_id = "system:system_test"
        config = await manager.get_cronjob_config(cronjob_id)

        assert config is not None
        assert config.identifier == "system_test"
        assert config.name == "System Test"
        assert config.cron == "0 5 * * *"
        assert config.second == "0"
        assert config.is_system is True
        assert config.status == CronJobStatus.ACTIVE
        assert isinstance(config.params, SystemCronParams)
        assert config.params.value == "default"
        assert manager.scheduler.get_job(cronjob_id) is not None

        with pytest.raises(ValueError, match="不能手动创建"):
            await manager.create_cronjob(
                identifier="system_test",
                params=SystemCronParams(),
                cron="0 0 * * *",
            )

        await manager.update_cronjob(
            cronjob_id=cronjob_id,
            identifier="system_test",
            params=SystemCronParams(value="changed"),
            cron="30 6 * * *",
            second="10",
            name="Renamed System Test",
        )

        updated = await manager.get_cronjob_config(cronjob_id)
        assert updated is not None
        assert updated.name == "Renamed System Test"
        assert updated.cron == "30 6 * * *"
        assert updated.second == "10"
        assert isinstance(updated.params, SystemCronParams)
        assert updated.params.value == "changed"
        assert updated.is_system is True

        with pytest.raises(ValueError, match="不能修改任务类型"):
            await manager.update_cronjob(
                cronjob_id=cronjob_id,
                identifier="other_test",
                params=SystemCronParams(),
                cron="0 0 * * *",
            )

        with pytest.raises(ValueError, match="不能暂停"):
            await manager.pause_cronjob(cronjob_id)

        with pytest.raises(ValueError, match="不能取消"):
            await manager.cancel_cronjob(cronjob_id)

        still_active = await manager.get_cronjob_config(cronjob_id)
        assert still_active is not None
        assert still_active.status == CronJobStatus.ACTIVE
    finally:
        await manager.shutdown()


async def test_system_cronjob_repairs_invalid_params_on_startup(
    cron_test_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = CronRegistry()
    registry.register_func(
        func=system_test_job,
        schema_cls=SystemCronParams,
        identifier="system_test",
        description="System test job",
        is_system=True,
        default_cron="0 5 * * *",
        default_second="0",
        default_params=SystemCronParams(value="default"),
        default_name="System Test",
    )

    async with cron_test_db() as session:
        await crud.create_cronjob(
            session,
            cronjob_id="system:system_test",
            identifier="system_test",
            name="System Test",
            cron="10 7 * * *",
            second="5",
            params_json="{",
            is_system=True,
        )

    import app.cron.manager as manager_module

    monkeypatch.setattr(manager_module, "cron_registry", registry)

    manager = CronManager()
    await manager.initialize()
    try:
        config = await manager.get_cronjob_config("system:system_test")

        assert config is not None
        assert config.cron == "10 7 * * *"
        assert config.second == "5"
        assert isinstance(config.params, SystemCronParams)
        assert config.params.value == "default"
        assert manager.scheduler.get_job("system:system_test") is not None
    finally:
        await manager.shutdown()
