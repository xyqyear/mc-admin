from sqlalchemy import select

from app.db.metadata import Base
from app.dynamic_config import ConfigProxy
from app.dynamic_config.models import DynamicConfig
from app.runtime import Runtime


async def test_config_reads_current_values_and_persists_to_own_database(tmp_path, isolated_runtime):
    runtimes = []
    for index in range(2):
        settings = isolated_runtime.settings.model_copy(deep=True)
        settings.database_url = f"sqlite+aiosqlite:///{tmp_path / f'config-{index}.sqlite3'}"
        runtimes.append(Runtime(settings))
    try:
        for runtime in runtimes:
            async with runtime.database.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        first = runtimes[0].resource("config_manager")
        second = runtimes[1].resource("config_manager")
        with runtimes[0].bind():
            view = ConfigProxy()
        with runtimes[1].bind():
            await first.initialize_all_configs()
            await second.initialize_all_configs()
            before = view.self_check
            values = before.model_dump()
            values["checks"]["dns_drift"] = False
            await first.update_config("self_check", values)
            assert view.self_check is not before
            assert not view.self_check.checks.dns_drift
            assert ConfigProxy(second).self_check.checks.dns_drift
        for index, runtime in enumerate(runtimes):
            async with runtime.database.session_factory() as session:
                stored = (await session.scalars(select(DynamicConfig).where(DynamicConfig.module_name == "self_check"))).one()
                assert stored.config_data["checks"]["dns_drift"] is (index == 1)
    finally:
        for runtime in runtimes:
            await runtime.close()
