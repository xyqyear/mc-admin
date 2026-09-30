import asyncio
from datetime import UTC, datetime

import pytest
from httpx2 import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import api_app
from app.minecraft import MCServerStatus
from app.runtime_resources import current_runtime
from app.world.locks import LockHolder, ServerOperationKind
from tests.support.regions import chunk_value, region_bytes

from .test_commands import complete

pytestmark = [pytest.mark.binary("restic"), pytest.mark.binary("fd")]


@pytest.fixture
async def http(world_case, monkeypatch):
    world_case.config.snapshots.time_restriction = type(
        "Restriction", (), {"enabled": False}
    )()
    monkeypatch.setattr(get_settings(), "master_token", "world-task-tests")
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
        headers={"Authorization": "Bearer world-task-tests"},
    ) as client:
        yield client


def target(kind="world"):
    return {
        "scope": {"kind": "world", "server_id": "survival", "selection": {"type": kind}}
    }


async def snapshot(http, case):
    response = await http.post("/api/snapshots", json=target())
    assert response.status_code == 202, response.text
    return (await complete(case, response.json()))["snapshot"]["id"]


async def test_world_create_eligible_restore_and_paginated_rollback_history(
    http, world_case
):
    case = world_case
    source = await snapshot(http, case)
    eligible = await http.post("/api/snapshots/eligible", json=target())
    assert eligible.status_code == 200
    assert source in [row["id"] for row in eligible.json()["snapshots"]]
    (case.region / "r.0.0.mca").write_bytes(region_bytes(["safety zero", "safety one"]))
    response = await http.post(
        "/api/snapshots/restorations",
        json={**target(), "source_snapshot_id": source, "entry_point": "world"},
    )
    assert response.status_code == 202, response.text
    accepted = response.json()
    await complete(case, accepted)
    assert chunk_value(case.region / "r.0.0.mca", 0) == "source zero"
    detail = await http.get("/api/snapshots/restorations/" + accepted["restoration_id"])
    assert detail.status_code == 200
    row = detail.json()
    assert row["operation_id"] == accepted["task_id"]
    assert row["scope"] == {
        "kind": "world",
        "server_id": "survival",
        "selection": {
            "type": "world",
            "region_dir_relpath": None,
            "regions": [],
            "chunks": [],
        },
    }
    assert row["server_generation"] > 0 and row["binding_issue"] is None
    assert (
        row["safety_snapshot_exists"]
        and row["rollback_available"]
        and row["entry_point"] == "world"
    )
    rolled = await http.post(f"/api/snapshots/restorations/{row['id']}/rollback")
    assert rolled.status_code == 202, rolled.text
    await complete(case, rolled.json())
    assert chunk_value(case.region / "r.0.0.mca", 0) == "safety zero"
    history = await http.get(
        "/api/snapshots/restorations?server_id=survival&limit=1&offset=0"
    )
    assert history.status_code == 200
    assert history.json()["total"] == 2 and len(history.json()["restorations"]) == 1
    assert history.json()["restorations"][0]["rollback_of_id"] == row["id"]


async def test_world_task_acceptance_returns_before_safety_and_keeps_maintenance(
    http, world_case, monkeypatch
):
    case = world_case
    source = await snapshot(http, case)
    creating, release = asyncio.Event(), asyncio.Event()
    original = case.snapshots.create_snapshot

    async def pause(*args, **kwargs):
        creating.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(case.snapshots, "create_snapshot", pause)
    response = await asyncio.wait_for(
        http.post(
            "/api/snapshots/restorations",
            json={**target(), "source_snapshot_id": source},
        ),
        2,
    )
    assert response.status_code == 202
    try:
        await asyncio.wait_for(creating.wait(), 2)
        row = await case.commands.store.get(response.json()["restoration_id"])
        assert row.safety_snapshot_id is None
        lock = current_runtime().resource("server_operation_lock")
        assert lock.is_locked("survival")
        blocked = await http.post("/api/snapshots", json=target())
        assert blocked.status_code == 423
    finally:
        release.set()
    await complete(case, response.json())
    assert not lock.is_locked("survival")


async def test_world_restore_requires_stopped_server_and_rejects_occupied_scope(
    http, world_case
):
    case = world_case
    source = await snapshot(http, case)
    before = (case.region / "r.0.0.mca").read_bytes()
    case.instance.status = MCServerStatus.RUNNING
    response = await http.post(
        "/api/snapshots/restorations", json={**target(), "source_snapshot_id": source}
    )
    assert response.status_code == 409
    case.instance.status = MCServerStatus.EXISTS
    lock = current_runtime().resource("server_operation_lock")
    holder = LockHolder(ServerOperationKind.RESTORE, datetime.now(UTC), 1, "恢复世界")
    async with lock.acquire("survival", holder):
        response = await http.post(
            "/api/snapshots/restorations",
            json={**target(), "source_snapshot_id": source},
        )
        assert response.status_code == 423
    assert (case.region / "r.0.0.mca").read_bytes() == before


async def test_world_ranges_and_history_validation_do_not_submit_writes(
    http, world_case
):
    for selection in [
        {"type": "dimension"},
        {"type": "regions", "region_dir_relpath": "world/region"},
        {"type": "chunks", "region_dir_relpath": "../region", "chunks": [[0, 0]]},
    ]:
        body = {
            "scope": {"kind": "world", "server_id": "survival", "selection": selection}
        }
        response = await http.post("/api/snapshots/eligible", json=body)
        assert response.status_code == 422
    for path, status in [
        ("/api/snapshots/restorations?limit=0", 422),
        ("/api/snapshots/restorations/missing", 404),
    ]:
        assert (await http.get(path)).status_code == status
    assert (
        await http.post("/api/snapshots/restorations/missing/rollback")
    ).status_code == 404
    assert not world_case.tasks.get_all_tasks()
