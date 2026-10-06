import asyncio
import sys

import pytest
from httpx2 import ASGITransport, AsyncClient

from app.config import get_settings
from app.dynamic_config import get_config
from app.dynamic_config.configs.mcmap import MCMapConfig
from app.main import api_app
from app.runtime_resources import current_runtime
from app.snapshots.restoration_models import RestorationType
from app.snapshots.selection_models import RestorationSelection

from .support import complete
from .test_previews import prepared

pytestmark = [pytest.mark.binary("restic"), pytest.mark.binary("fd")]


@pytest.fixture
async def http(world_case, monkeypatch):
    world_case.config.mcmap = MCMapConfig()
    monkeypatch.setattr(get_settings(), "master_token", "preview-task-tests")
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test", headers={"Authorization": "Bearer preview-task-tests"}) as client:
        yield client


async def prepare_http(http, case):
    target, scope, source = await prepared(case)
    response = await http.post("/api/snapshots/previews", json={"scope": scope.model_dump(mode="json"), "source_snapshot_id": source})
    assert response.status_code == 202, response.text
    result = await complete(case, response.json())
    return target, source, result["preview_id"]


async def test_preview_metadata_pages_heartbeat_and_cleanup_tasks(http, world_case):
    case = world_case
    target, source, preview_id = await prepare_http(http, case)
    base = f"/api/snapshots/previews/{preview_id}"
    detail = await http.get(base)
    assert detail.status_code == 200 and detail.json()["kind"] == "files"
    tasks_before = len(case.tasks.get_all_tasks())
    for invalid_id in ("--keep-last=0", "latest", source[:8]):
        assert (await http.delete("/api/snapshots/" + invalid_id)).status_code == 422
    assert len(case.tasks.get_all_tasks()) == tasks_before
    page = await http.get(base + "/actions", params={"limit": 1})
    assert page.status_code == 200 and page.json()["actions"][0]["action"] == "updated"
    assert page.json()["next_cursor"] is None
    invalid = await http.get(base + "/actions", params={"limit": 201})
    assert invalid.status_code == 422
    heartbeat = await http.post(base + "/heartbeat")
    assert heartbeat.status_code == 204
    delete = await http.delete("/api/snapshots/" + source)
    assert delete.status_code == 423
    unknown = await http.post("/api/snapshots/previews/unknown/heartbeat")
    assert unknown.status_code == 404
    tile = await http.get(base + "/tiles/0/0.png")
    assert tile.status_code == 404
    previews = current_runtime().snapshot_previews
    assert previews is not None
    directory = previews.manager.get_session_dir(preview_id)
    assert directory is not None
    closed = await http.delete(base)
    assert closed.status_code == 202
    await complete(case, closed.json())
    assert not directory.exists()
    assert (await http.get(base)).status_code == 404
    await complete(case, (await http.delete(base)).json())
    assert (target / "000.txt").read_text() == "live value 0"


async def test_previews_require_authentication_and_validate_scope_before_task(http, world_case):
    response = await http.post("/api/snapshots/previews", headers={"Authorization": "Bearer invalid"}, json={"scope": {"kind": "global"}, "source_snapshot_id": "a" * 64})
    assert response.status_code == 401
    invalid = await http.post("/api/snapshots/previews", json={"scope": {"kind": "paths", "server_id": "survival", "paths": ["../outside"]}, "source_snapshot_id": "a" * 64})
    assert invalid.status_code == 422
async def test_preview_tile_renders_staged_snapshot_through_owned_queue(
    http: AsyncClient,
    world_case,
    tmp_path,
    monkeypatch,
):
    from app.mcmap import runner
    from app.mcmap.cache import ServerMapCache
    from app.operations.journal_types import OperationState

    case = world_case
    data_path = case.data
    previews = current_runtime().snapshot_previews
    assert previews is not None
    cache = ServerMapCache(data_path)
    cache.cache_dir.mkdir()
    cache.palette_json.write_text("{}")
    live_tiles = cache.tiles_dir("world/region")
    live_tiles.mkdir(parents=True)
    (live_tiles / "r.0.0.png").write_bytes(b"live tile remains intact")
    executable = tmp_path / "owned-preview-renderer"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "from pathlib import Path\n"
        "out = Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "assert 'source' in str(sys.argv), sys.argv\n"
        "(out / 'r.0.0.png').write_bytes(b'\\x89PNG\\r\\n\\x1a\\npreview-rendered')\n"
        "print(json.dumps(dict(type='region', x=0, z=0, status='rendered')), flush=True)\n"
    )
    executable.chmod(0o700)
    monkeypatch.setattr(runner.get_settings(), "mcmap_binary_path", executable)
    monkeypatch.setattr(runner.get_settings(), "server_path", data_path.parent.parent)
    journal = case.journal
    monkeypatch.setattr(get_config().mcmap, "batch_size", 1)
    monkeypatch.setattr(get_config().mcmap, "thread_count", 1)
    monkeypatch.setattr(get_config().mcmap, "request_timeout_seconds", 10)
    selection = RestorationSelection(
        type=RestorationType.REGIONS,
        region_dir_relpath="world/region",
        regions=[(0, 0)],
    )
    source = await asyncio.wait_for(
        case.snapshots.create_snapshot([data_path / "world"]), 30
    )
    response = await asyncio.wait_for(
        http.post(
            "/api/snapshots/previews",
            json={
                "source_snapshot_id": source.id,
                "scope": {"kind": "world", "server_id": "survival", "selection": selection.model_dump()},
            },
        ),
        30,
    )
    assert response.status_code == 202, response.text
    result = await complete(case, response.json())
    session_id = result["preview_id"]
    directory = previews.manager.get_session_dir(session_id)
    assert directory is not None
    assert not (directory / "tiles/r.0.0.png").exists()
    try:
        response = await http.get(
            f"/api/snapshots/previews/{session_id}/tiles/0/0.png",
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "image/png"
        assert response.content == b"\x89PNG\r\n\x1a\npreview-rendered"
        assert (live_tiles / "r.0.0.png").read_bytes() == b"live tile remains intact"
        records = [
            record
            for record in await journal.list()
            if record.kind == "world_preview_render"
        ]
        assert len(records) == 1
        assert records[0].state is OperationState.SUCCEEDED
        assert all(
            resource.server_id == "survival" and resource.generation == 1
            for resource in records[0].resources
        )
        assert all(reference.resolved for reference in records[0].recovery_refs)
    finally:
        response = await http.delete(
            f"/api/snapshots/previews/{session_id}"
        )
        assert response.status_code == 202
        await complete(case, response.json())
    assert not directory.exists()


@pytest.mark.parametrize("role", ["admin", "owner"])
async def test_preview_and_maintenance_cookie_permissions_preserve_data_without_csrf(
    http, world_case, monkeypatch, role,
):
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock

    from app.auth.models import UserRole
    from app.auth.schemas import UserPublic
    from app.auth.service import get_identity_service, user_from_claims
    from app.auth.session import AUTH_COOKIE_NAME, CSRF_COOKIE_NAME, CSRF_HEADER_NAME
    from app.main import app

    case = world_case
    target, source, preview_id = await prepare_http(http, case)
    identity = get_identity_service()
    monkeypatch.setattr(identity, "get_current_session_user", AsyncMock(side_effect=user_from_claims))
    user = UserPublic(id=42, username=role, role=UserRole(role), created_at=datetime.now(UTC))
    token, csrf = identity.create_session_token(user)
    base = f"/api/snapshots/previews/{preview_id}"
    mutations = [
        ("POST", "/api/snapshots/targets/check", {"scope": {"kind": "global"}}),
        ("POST", "/api/snapshots/previews", {"scope": {"kind": "global"}, "source_snapshot_id": source}),
        ("POST", base + "/heartbeat", None),
        ("DELETE", base, None),
        ("DELETE", "/api/snapshots/" + source, None),
        ("POST", "/api/snapshots/unlock", None),
    ]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        before = len(case.tasks.get_all_tasks())
        for method, path, body in mutations:
            assert (await client.request(method, path, json=body)).status_code == 401
        for path in (base, base + "/actions", base + "/tiles/0/0.png", "/api/snapshots/restorations/active"):
            assert (await client.get(path)).status_code == 401
        client.cookies.set(AUTH_COOKIE_NAME, token, path="/api")
        client.cookies.set(CSRF_COOKIE_NAME, csrf, path="/")
        for method, path, body in mutations:
            assert (await client.request(method, path, json=body)).status_code == 403
        assert len(case.tasks.get_all_tasks()) == before
        assert (await client.get(base)).status_code == 200
        assert (await client.get(base + "/actions")).status_code == 200
        assert (target / "000.txt").read_text() == "live value 0"
        assert source in {snapshot.id for snapshot in await case.snapshots.list_snapshots()}
        client.headers[CSRF_HEADER_NAME] = csrf
        assert (await client.post("/api/snapshots/targets/check", json={"scope": {"kind": "global"}})).status_code == 200
        assert (await client.get("/api/snapshots/restorations/active")).status_code == 200
        assert (await client.post(base + "/heartbeat")).status_code == 204
        await complete(case, (await client.delete(base)).json())
        assert (await client.get(base)).status_code == 404
        await complete(case, (await client.post("/api/snapshots/unlock")).json())
        await complete(case, (await client.delete("/api/snapshots/" + source)).json())
        assert source not in {snapshot.id for snapshot in await case.snapshots.list_snapshots()}
