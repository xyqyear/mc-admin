from dataclasses import replace

from sqlalchemy import func, select

from app.db.metadata import Base
from app.errors import INTERNAL_ERROR_MESSAGE
from app.runtime import Runtime
from app.self_check.checks import CHECK_DEFINITIONS
from app.self_check.models import SelfCheckFinding, SelfCheckRun


async def test_health_run_keeps_dependencies_and_history_owned_and_isolates_failures(tmp_path, isolated_runtime, caplog):
    secret = "synthetic-health-adapter-credential"
    runtimes = []
    for index in range(2):
        settings = isolated_runtime.settings.model_copy(deep=True)
        settings.database_url = f"sqlite+aiosqlite:///{tmp_path / f'health-{index}.sqlite3'}"
        if index == 0:
            settings.fd_binary_path = tmp_path / "missing-owned-fd"
        runtimes.append(Runtime(settings))
    delivered = []

    async def failing_check(context):
        raise RuntimeError(secret)

    class BrokenSink:
        async def publish(self, result):
            raise RuntimeError(secret)

    class RecordingSink:
        async def publish(self, result):
            delivered.append(result)

    try:
        for runtime in runtimes:
            async with runtime.database.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            await runtime.resource("config_manager").initialize_all_configs()
        service = runtimes[0].resource("self_check_service")
        storage = "storage.server_directory_usage"
        binary = "dependency.binaries"
        service.definitions = {
            storage: replace(CHECK_DEFINITIONS[storage], function=failing_check),
            binary: CHECK_DEFINITIONS[binary],
        }
        service.check_ids = tuple(service.definitions)
        service.notifications.register(BrokenSink())
        service.notifications.register(RecordingSink())
        with runtimes[1].bind():
            events = [event async for event in service.iter_self_check_events(trigger="manual", requested_by_user_id=73)]
            result = events[-1].result
            assert result is not None
            assert [event.type for event in events] == [
                "started", "check_started", "check_finished", "check_started", "check_finished", "completed",
            ]
            assert [finding.status for finding in result.findings] == ["failed", "warning"]
            assert result.findings[0].evidence == {"error": INTERNAL_ERROR_MESSAGE}
            assert str(tmp_path / "missing-owned-fd") in result.findings[1].model_dump_json()
            assert delivered == [result]
            assert secret not in result.model_dump_json()
            assert secret not in caplog.text
            for index, runtime in enumerate(runtimes):
                async with runtime.database.session_factory() as session:
                    assert await session.scalar(select(func.count()).select_from(SelfCheckRun)) == (1 if index == 0 else 0)
                    findings = list(await session.scalars(select(SelfCheckFinding)))
                    assert all(secret not in finding.evidence_json for finding in findings)
                    if index == 0:
                        run = await session.get(SelfCheckRun, result.id)
                        assert run is not None and run.requested_by_user_id == 73

            manager = runtimes[0].resource("config_manager")
            values = service.dependencies.configuration.self_check.model_dump()
            values["checks"]["dependency_binaries"] = False
            await manager.update_config("self_check", values)
            next_run = await service.run_self_check(trigger="manual", check_ids=(binary,), scope="check")
            assert next_run.findings[0].status == "skipped"
    finally:
        for runtime in runtimes:
            await runtime.close()
