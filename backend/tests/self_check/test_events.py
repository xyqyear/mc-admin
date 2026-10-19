import asyncio

import pytest
from sqlalchemy import select

from app.self_check.checks import CHECK_DEFINITIONS
from app.self_check.constants import SERVER_CREATED_TRIGGER
from app.self_check.events import schedule_self_check_event
from app.self_check.models import SelfCheckFinding, SelfCheckRun


async def test_event_trigger_skips_when_config_is_unavailable(database, isolated_runtime, monkeypatch):
    class UnavailableConfig:
        @property
        def self_check(self):
            raise RuntimeError("ConfigManager not initialized")

    monkeypatch.setattr(isolated_runtime, "_dynamic_configuration", UnavailableConfig())
    schedule_self_check_event(SERVER_CREATED_TRIGGER, requested_by_user_id=1)

    assert not isolated_runtime._background
    async with database.session_factory() as session:
        assert list(await session.scalars(select(SelfCheckRun))) == []


@pytest.mark.parametrize("enabled", [True, False])
async def test_event_trigger_persists_owned_run_only_when_enabled(
    database, runtime_config, isolated_runtime, enabled,
):
    values = runtime_config.self_check.model_dump()
    values["event_triggers"]["after_server_created"] = enabled
    await isolated_runtime.config_manager.update_config("self_check", values)
    service = isolated_runtime.self_check_service
    service.definitions = {"dependency.binaries": CHECK_DEFINITIONS["dependency.binaries"]}
    service.check_ids = tuple(service.definitions)

    schedule_self_check_event(SERVER_CREATED_TRIGGER, requested_by_user_id=73)
    pending = tuple(isolated_runtime._background)
    assert bool(pending) is enabled
    if pending:
        await asyncio.wait_for(asyncio.gather(*pending), timeout=5)
    assert not isolated_runtime._background

    async with database.session_factory() as session:
        rows = list(await session.scalars(select(SelfCheckRun)))
        assert len(rows) == int(enabled)
        findings = list(await session.scalars(select(SelfCheckFinding)))
        if enabled:
            assert rows[0].trigger == SERVER_CREATED_TRIGGER
            assert rows[0].requested_by_user_id == 73
            assert rows[0].finished_at is not None
            assert findings and all(row.check_id == "dependency.binaries" for row in findings)
        else:
            assert findings == []
