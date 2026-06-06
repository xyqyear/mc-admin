from types import SimpleNamespace

import pytest

from app.dynamic_config.configs.self_check import SelfCheckConfig
from app.self_check.constants import SERVER_CREATED_TRIGGER


def test_event_trigger_skips_when_config_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.self_check.events as events_module

    class UnavailableConfig:
        @property
        def self_check(self):
            raise RuntimeError("ConfigManager not initialized")

    def fail_create_task(coro):
        coro.close()
        raise AssertionError("event-triggered self-check should not be scheduled")

    monkeypatch.setattr(events_module, "config", UnavailableConfig())
    monkeypatch.setattr(events_module.asyncio, "create_task", fail_create_task)

    events_module.schedule_self_check_event(SERVER_CREATED_TRIGGER, requested_by_user_id=1)


def test_event_trigger_schedules_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.self_check.events as events_module

    scheduled = []

    def capture_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr(
        events_module,
        "config",
        SimpleNamespace(self_check=SelfCheckConfig()),
    )
    monkeypatch.setattr(events_module.asyncio, "create_task", capture_create_task)

    events_module.schedule_self_check_event(SERVER_CREATED_TRIGGER, requested_by_user_id=1)

    assert len(scheduled) == 1
