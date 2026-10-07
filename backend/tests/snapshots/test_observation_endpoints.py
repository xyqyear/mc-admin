import asyncio
from unittest.mock import AsyncMock

import pytest
from httpx2 import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import api_app
from app.snapshots.scopes import scope_adapter

pytestmark = [pytest.mark.binary("restic"), pytest.mark.binary("fd")]


@pytest.fixture
async def http(world_case, monkeypatch):
    monkeypatch.setattr(get_settings(), "master_token", "snapshot-observation")
    async with AsyncClient(
        transport=ASGITransport(app=api_app), base_url="http://test",
        headers={"Authorization": "Bearer snapshot-observation"},
    ) as client:
        yield client


@pytest.mark.parametrize("kind", ["paths", "global"])
async def test_active_history_observes_queued_and_running_work_without_restic(
    http, world_case, monkeypatch, kind
):
    case = world_case
    target = case.data / "settings.txt"
    target.write_text("source")
    scope = {"kind": "global"} if kind == "global" else {
        "kind": "paths", "server_id": "survival", "paths": ["settings.txt"]
    }
    source = await case.snapshots.create_snapshot(
        [case.data.parent.parent if kind == "global" else target]
    )
    target.write_text("live")
    start, safety = asyncio.Event(), asyncio.Event()
    original_start = case.journal.start

    async def queued(operation_id):
        await start.wait()
        return await original_start(operation_id)

    async def preparing_safety(*_args, **_kwargs):
        safety.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(case.journal, "start", queued)
    monkeypatch.setattr(case.snapshots, "create_snapshot", preparing_safety)
    response = await http.post("/api/snapshots/restorations", json={
        "scope": scope, "source_snapshot_id": source.id, "entry_point": "files",
    })
    assert response.status_code == 202, response.text
    accepted = response.json()
    active_url = "/api/snapshots/restorations/active?server_id=survival"
    try:
        with monkeypatch.context() as patch:
            patch.setattr(case.snapshots, "list_snapshots", AsyncMock(side_effect=OSError("repository unavailable")))
            pending = await http.get(active_url)
            assert pending.status_code == 200, pending.text
            assert pending.json() == {"total": 1, "restorations": [{
                "id": accepted["restoration_id"], "operation_id": accepted["task_id"],
                "scope": scope_adapter.validate_python(scope).model_dump(mode="json"), "status": "pending",
            }]}
            empty = await http.get(active_url + "&limit=1&offset=1")
            assert empty.json() == {"total": 1, "restorations": []}
            unrelated = await http.get("/api/snapshots/restorations/active?server_id=other")
            assert unrelated.json() == {"total": 0, "restorations": []}
        start.set()
        await asyncio.wait_for(safety.wait(), 10)
        with monkeypatch.context() as patch:
            patch.setattr(case.snapshots, "list_snapshots", AsyncMock(side_effect=OSError("repository unavailable")))
            running = await http.get(active_url)
            assert running.status_code == 200
            assert running.json()["restorations"][0]["status"] == "running"
        history = await http.get(f"/api/snapshots/restorations?server_id=survival&kind={kind}&status=running&entry_point=files")
        assert history.status_code == 200, history.text
        assert history.json()["total"] == 1
        row = history.json()["restorations"][0]
        assert row["id"] == accepted["restoration_id"]
        assert row["targets"] == [{"server_id": "survival", "generation": 1}]
        assert not row["rollback_available"]
        for query in ("kind=world", "status=succeeded", "entry_point=world", "server_id=other"):
            assert (await http.get("/api/snapshots/restorations?" + query)).json()["total"] == 0
        assert target.read_text() == "live"
    finally:
        start.set()
        await case.tasks.cancel(accepted["task_id"])
        await asyncio.wait_for(case.tasks.get_future(accepted["task_id"]), 10)
    assert (await http.get(active_url)).json() == {"total": 0, "restorations": []}
    cancelled = await http.get("/api/snapshots/restorations?status=cancelled")
    assert cancelled.json()["total"] == 1
    assert target.read_text() == "live"


@pytest.mark.parametrize("body", [
    {"scope": {"kind": "global"}},
    {"scope": {"kind": "server", "server_id": "survival"}},
    {"scope": {"kind": "paths", "server_id": "survival", "paths": ["plugins"]}},
    {"scope": {"kind": "world", "server_id": "survival", "selection": {"type": "dimension", "region_dir_relpath": "world/region"}}, "note": "创建备注不属于范围检查"},
])
async def test_world_target_feedback_rejects_unused_file_and_project_scopes(
    http, world_case, body,
):
    response = await http.post("/api/snapshots/targets/check", json=body)
    assert response.status_code == 422
    assert world_case.tasks.get_all_tasks() == []
    assert await world_case.journal.list() == []


async def test_target_feedback_protects_external_chunk_payload_as_one_unit(http, world_case):
    case = world_case
    case.config.snapshots.ignored_paths = [
        f"world/{directory}/c.0.0.mcc" for directory in ("region", "entities", "poi")
    ]
    scope = {"kind": "world", "server_id": "survival", "selection": {
        "type": "chunks", "region_dir_relpath": "world/region", "chunks": [[0, 0]],
    }}
    denied = await http.post("/api/snapshots/targets/check", json={"scope": scope})
    assert denied.status_code == 200 and not denied.json()["allowed"]
    scope["selection"]["chunks"] = [[0, 0], [1, 0]]
    mixed = await http.post("/api/snapshots/targets/check", json={"scope": scope})
    assert mixed.status_code == 200 and mixed.json()["allowed"]
    assert mixed.json()["skipped_count"] > 0
