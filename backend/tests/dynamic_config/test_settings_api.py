import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.dynamic_config.manager import create_config_manager
from app.main import app, create_api_app
from app.routers.settings import router
from app.runtime_resources import current_runtime


@pytest.fixture
async def settings_manager(monkeypatch, db_session_factory):
    manager = create_config_manager(session_factory=db_session_factory)
    monkeypatch.setattr(current_runtime(), "_config_manager", manager)
    await manager.initialize_all_configs()
    return manager


@pytest.fixture
def settings_client(monkeypatch):
    monkeypatch.setattr(get_settings(), "master_token", "settings-test-token")
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()


HEADERS = {"Authorization": "Bearer settings-test-token"}
RESOURCES = ["dns", "snapshots", "log-parser", "players", "mcmap", "world", "self-check"]


@pytest.mark.parametrize("resource,patch", [
    ("dns", {"enabled": False, "dns": {"type": "dnspod", "domain": "example.test", "id": "fixture", "key": "fixture"}, "addresses": [{"type": "manual", "name": "play", "record_type": "AAAA", "value": "::1", "port": 25565}]}),
    ("snapshots", {"time_restriction": {"enabled": False, "before_seconds": 0, "after_seconds": 12}, "ignored_paths": ["config"]}),
    ("log-parser", {"join_pattern": "joined (\\w+)", "achievement_patterns": ["(\\w+) earned (.+)"]}),
    ("players", {"ignored_name_prefixes": ["fixture_"], "query": {"query_command": "printf fixture", "timeout": 0.5}}),
    ("mcmap", {"batch_size": 7, "prune_default_threshold_seconds": 0}),
    ("world", {"region_stat_workers": 3, "dimension_labels": {".": "自定义世界", "DIM-1": "下界"}}),
    ("self-check", {"retention_runs_keep_days": 21, "backup_mod_ids": ["FTBBackups"]}),
])
async def test_settings_replace_reload_and_reset(resource, patch, settings_manager, settings_client):
    path = f"/api/settings/{resource}"
    original = settings_client.get(path, headers=HEADERS)
    assert original.status_code == 200
    authored = {**original.json(), **patch}
    if resource == "self-check":
        authored["checks"] = {**original.json()["checks"], "dns_drift": False}
    saved = settings_client.put(path, headers=HEADERS, json=authored)
    assert saved.status_code == 200, saved.text
    effective = saved.json()
    expected = {**authored}
    if resource == "self-check":
        expected["backup_mod_ids"] = ["ftbbackups"]
    assert effective == expected
    assert settings_client.get(path, headers=HEADERS).json() == effective
    reloaded = create_config_manager(session_factory=settings_manager.session_factory)
    await reloaded.initialize_all_configs()
    assert reloaded.get_config(resource.replace("-", "_")).model_dump() == effective
    reset = settings_client.post(f"{path}/reset", headers=HEADERS)
    assert reset.status_code == 200
    assert reset.json() == original.json()
    assert settings_client.get(path, headers=HEADERS).json() == original.json()


async def test_invalid_settings_preserve_persisted_and_runtime_values(settings_manager, settings_client):
    path = "/api/settings/world"
    original = settings_client.get(path, headers=HEADERS).json()
    for invalid in ("invalid", 0, 257):
        response = settings_client.put(path, headers=HEADERS, json={**original, "region_stat_workers": invalid})
        assert response.status_code == 422
        assert settings_client.get(path, headers=HEADERS).json() == original
    assert settings_client.put(path, headers=HEADERS, json={"unexpected": True}).status_code == 422
    assert settings_client.get(path, headers=HEADERS).json() == original
    reloaded = create_config_manager(session_factory=settings_manager.session_factory)
    await reloaded.initialize_all_configs()
    assert reloaded.get_config("world").model_dump() == original


async def test_settings_errors_do_not_echo_mapping_keys_or_unrecognized_fields(settings_manager, settings_client, caplog):
    path = "/api/settings/world"
    original = settings_client.get(path, headers=HEADERS).json()
    for invalid in (
        {**original, "dimension_labels": {"private-key-secret": {"value": "private-input-secret"}}},
        {**original, "private-field-secret": "private-input-secret"},
    ):
        response = settings_client.put(path, headers=HEADERS, json=invalid)
        assert response.status_code == 422
        assert "private-" not in response.text + caplog.text
        assert settings_client.get(path, headers=HEADERS).json() == original


async def test_settings_validation_follows_router_under_another_prefix(settings_manager, settings_client):
    application = create_api_app(current_runtime())
    application.include_router(router, prefix="/relocated")
    with TestClient(application) as client:
        original = client.get("/api/settings/world", headers=HEADERS).json()
        response = client.put("/api/relocated/settings/world", headers=HEADERS, json={
            **original, "region_stat_workers": "private-input-secret",
        })
        assert response.status_code == 422
        assert response.json() == {"detail": "配置参数无效: region_stat_workers: 请输入整数"}
        assert "private-input-secret" not in response.text
        assert client.get("/api/settings/world", headers=HEADERS).json() == original


@pytest.mark.parametrize("provider", [
    {"type": "huawei", "domain": "example.test", "ak": "fixture", "sk": "fixture", "region": "cn-south-1"},
    {"type": "dnspod", "domain": "example.test", "id": "fixture", "key": "fixture"},
])
async def test_dns_provider_contract_and_rejected_values(provider, settings_manager, settings_client):
    path = "/api/settings/dns"
    original = settings_client.get(path, headers=HEADERS).json()
    saved = settings_client.put(path, headers=HEADERS, json={**original, "dns": provider})
    assert saved.status_code == 200
    assert saved.json()["dns"] == provider
    assert settings_client.get(path, headers=HEADERS).json()["dns"] == provider
    for invalid in ({"type": "unsupported"}, {**provider, "domain": []}):
        assert settings_client.put(path, headers=HEADERS, json={**original, "dns": invalid}).status_code == 422
        assert settings_client.get(path, headers=HEADERS).json()["dns"] == provider


async def test_parser_save_validation_and_notification(settings_manager, settings_client):
    path = "/api/settings/log-parser"
    original = settings_client.get(path, headers=HEADERS).json()
    notifications = []
    unsubscribe = settings_manager.listen("log_parser", lambda: notifications.append(settings_manager.get_config("log_parser").model_dump()))
    invalid = {**original, "chat_pattern": "no capture groups"}
    assert settings_client.put(path, headers=HEADERS, json=invalid).status_code == 400
    assert settings_client.get(path, headers=HEADERS).json() == original
    assert notifications == []
    valid = {**original, "chat_pattern": "(prefix) (player) (message)"}
    assert settings_client.put(path, headers=HEADERS, json=valid).status_code == 200
    assert notifications == [valid]
    unsubscribe()


@pytest.mark.parametrize("resource", RESOURCES)
async def test_settings_require_authentication(resource, settings_manager, settings_client):
    path = f"/api/settings/{resource}"
    original = settings_client.get(path, headers=HEADERS).json()
    assert settings_client.get(path).status_code == 401
    assert settings_client.put(path, json=original).status_code == 401
    assert settings_client.post(f"{path}/reset").status_code == 401
    assert settings_client.get(path, headers=HEADERS).json() == original
