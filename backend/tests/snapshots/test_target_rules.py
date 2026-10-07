from unittest.mock import AsyncMock

import pytest
from httpx2 import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import api_app

pytestmark = pytest.mark.binary("restic")


@pytest.fixture
async def http(case, monkeypatch):
    monkeypatch.setattr(get_settings(), "master_token", "snapshot-rules")
    async with AsyncClient(
        transport=ASGITransport(app=api_app), base_url="http://test",
        headers={"Authorization": "Bearer snapshot-rules"},
    ) as client:
        yield client


async def test_rules_are_relative_expanded_and_do_not_follow_links(http, case, monkeypatch):
    (case.data / "target").mkdir()
    (case.data / "alias").symlink_to("target", target_is_directory=True)
    case.config.snapshots.ignored_paths = ["alias", "<LEVEL_NAME>/playerdata", "alias"]
    monkeypatch.setattr(case.client, "_run", AsyncMock(side_effect=AssertionError("rules must not invoke Restic")))
    response = await http.get("/api/snapshots/targets/rules?server_id=survival")
    assert response.status_code == 200, response.text
    rules = response.json()
    assert rules["server_id"] == "survival"
    assert rules["server_generation"] == 1
    assert rules["ignored_paths"] == ["alias", "world/playerdata"]
    assert len(rules["rules_version"]) == 64
    assert len(case.tasks.get_all_tasks()) == 0
    assert await case.journal.list() == []
    (case.data / "alias").unlink()
    (case.data / "other").mkdir()
    (case.data / "alias").symlink_to("other", target_is_directory=True)
    unchanged = await http.get("/api/snapshots/targets/rules?server_id=survival")
    assert unchanged.json() == rules
    (case.data / "server.properties").write_text("level-name=renamed\n")
    updated = (await http.get("/api/snapshots/targets/rules?server_id=survival")).json()
    assert updated["ignored_paths"] == ["alias", "renamed/playerdata"]
    assert updated["rules_version"] != rules["rules_version"]


async def test_rules_require_authentication_and_registered_server(http, case):
    endpoint = "/api/snapshots/targets/rules"
    assert (await http.get(endpoint + "?server_id=survival", headers={"Authorization": "Bearer invalid"})).status_code == 401
    assert (await http.get(endpoint + "?server_id=unknown")).status_code == 404
    assert (await http.get(endpoint + "?server_id=../survival")).status_code == 400
    assert (await http.get(endpoint)).status_code == 422
    assert (await http.get(endpoint + "?server_id=")).status_code == 422
    assert case.tasks.get_all_tasks() == []
    assert await case.journal.list() == []
