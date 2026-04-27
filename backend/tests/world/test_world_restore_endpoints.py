"""End-to-end tests for the world-restore router using httpx.AsyncClient.

These exercise the HTTP/SSE surface against a real ``WorldRestoreOrchestrator``
backed by a real restic repository and a real ``mcmap`` binary (chunks-scope
tests skip themselves if mcmap is unavailable). The Docker side of MCInstance
is replaced with a fake instance so tests don't need containers.

We use ``httpx.AsyncClient`` with ``ASGITransport`` (rather than the synchronous
``TestClient``) so the request handler runs in the same event loop as the test
— that's what lets the per-server ``asyncio.Lock`` tests observe each other's
state.
"""

import json
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Iterator
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.main import api_app
from app.minecraft import MCServerStatus
from app.models import (
    Base,
    Restoration,
    RestorationSelection,
    RestorationStatus,
    RestorationType,
)
from app.snapshots.restic import ResticManager
from app.utils.exec import exec_command
from app.world import (
    ServerOperationKind,
    ServerOperationLock,
    WorldRestoreOrchestrator,
)
from app.world.locks import LockHolder


def _restic_available() -> bool:
    try:
        result = subprocess.run(
            ["restic", "version"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _mcmap_available() -> bool:
    try:
        result = subprocess.run(
            ["mcmap", "--version"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


pytestmark = pytest.mark.skipif(
    not _restic_available(), reason="restic not installed"
)


# --- Fakes ------------------------------------------------------------------


class _FakeInstance:
    def __init__(self, data_path: Path, project_path: Path) -> None:
        self._data_path = data_path
        self._project_path = project_path
        self._status = MCServerStatus.EXISTS
        self._exists = True

    def get_data_path(self) -> Path:
        return self._data_path

    def get_project_path(self) -> Path:
        return self._project_path

    async def exists(self) -> bool:
        return self._exists

    async def get_status(self) -> MCServerStatus:
        return self._status

    def set_status(self, status: MCServerStatus) -> None:
        self._status = status


class _FakeDockerMC:
    def __init__(self, instance: _FakeInstance) -> None:
        self._instance = instance

    def get_instance(self, server_id: str) -> _FakeInstance:
        return self._instance


def _empty_mca() -> bytes:
    return b"\x00" * 8192


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture
def data_path() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="mc-restore-endpoint-data-") as tmp:
        data = Path(tmp)
        world = data / "world"
        ow_region = world / "region"
        ow_region.mkdir(parents=True)
        (ow_region / "r.0.0.mca").write_bytes(_empty_mca())
        (ow_region / "r.1.0.mca").write_bytes(_empty_mca() + b"\xab\xcd")
        (world / "level.dat").write_bytes(b"level-stub")
        (world / "entities").mkdir(parents=True)
        (world / "entities" / "r.0.0.mca").write_bytes(_empty_mca())
        nether_region = world / "DIM-1" / "region"
        nether_region.mkdir(parents=True)
        (nether_region / "r.0.0.mca").write_bytes(_empty_mca() + b"\xee\xff")
        yield data


@pytest.fixture
def project_path(data_path: Path) -> Path:
    return data_path.parent


@pytest.fixture
def repo_path() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="mc-restore-endpoint-repo-") as tmp:
        yield Path(tmp)


@pytest_asyncio.fixture
async def restic_manager(repo_path: Path) -> ResticManager:
    manager = ResticManager(repository_path=str(repo_path), password=None)
    await exec_command("restic", "init", "--insecure-no-password", env=manager.env)
    return manager


@pytest_asyncio.fixture
async def session_factory():
    with tempfile.TemporaryDirectory(prefix="mc-restore-endpoint-db-") as tmp:
        db_path = Path(tmp) / "test.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            yield maker
        finally:
            await engine.dispose()


@pytest.fixture
def fake_instance(data_path: Path, project_path: Path) -> _FakeInstance:
    return _FakeInstance(data_path, project_path)


@pytest.fixture
def fake_docker(fake_instance: _FakeInstance) -> _FakeDockerMC:
    return _FakeDockerMC(fake_instance)


@pytest.fixture
def lock() -> ServerOperationLock:
    return ServerOperationLock()


@pytest.fixture
def orchestrator(restic_manager, fake_docker, lock, session_factory):
    return WorldRestoreOrchestrator(
        restic_manager=restic_manager,
        docker_mc_manager=fake_docker,
        server_operation_lock=lock,
        session_factory=session_factory,
    )


@contextmanager
def _patch_router(orchestrator, fake_docker, lock, session_factory):
    """Patch every module-level dependency the router reaches into."""
    import app.world as world_module
    from app.routers.servers import world_restore as world_restore_module

    saved = world_module.world_restore_orchestrator
    saved_lock = world_module.server_operation_lock
    world_module.world_restore_orchestrator = orchestrator
    world_module.server_operation_lock = lock
    try:
        with (
            patch.object(
                world_restore_module, "docker_mc_manager", fake_docker
            ),
            patch.object(
                world_restore_module, "get_async_session", session_factory
            ),
            patch("app.dependencies.settings") as mock_dep_settings,
        ):
            mock_dep_settings.master_token = "test_master_token"
            yield
    finally:
        world_module.world_restore_orchestrator = saved
        world_module.server_operation_lock = saved_lock


@pytest_asyncio.fixture
async def http(
    orchestrator, fake_docker, lock, session_factory
) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with _patch_router(orchestrator, fake_docker, lock, session_factory):
            yield client


def _auth() -> dict[str, str]:
    return {"Authorization": "Bearer test_master_token"}


def _parse_sse_lines(body: str) -> list[dict]:
    events: list[dict] = []
    for block in body.strip().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
    return events


# --- Layout ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_layout_returns_world_roots(http: AsyncClient):
    response = await http.get("/api/servers/srv1/world-restore/layout", headers=_auth())
    assert response.status_code == 200
    data = response.json()
    assert "world_roots" in data
    assert len(data["world_roots"]) == 1
    root = data["world_roots"][0]
    assert root["name"] == "world"
    labels = {d["label"] for d in root["dimensions"]}
    assert labels == {"Overworld", "Nether"}


# --- Eligible snapshots ----------------------------------------------------


@pytest.mark.asyncio
async def test_eligible_snapshots_filters_by_coverage(
    http: AsyncClient, orchestrator
):
    selection = RestorationSelection(type=RestorationType.WORLD)
    snap = await orchestrator.create_snapshot("srv1", selection, user_id=None)

    response = await http.post(
        "/api/servers/srv1/world-restore/eligible-snapshots",
        headers=_auth(),
        json=selection.model_dump(),
    )
    assert response.status_code == 200
    data = response.json()
    assert any(s["id"] == snap.id for s in data["snapshots"])


# --- Snapshot creation -----------------------------------------------------


@pytest.mark.asyncio
async def test_create_snapshot_endpoint(http: AsyncClient):
    selection = RestorationSelection(type=RestorationType.WORLD)
    response = await http.post(
        "/api/servers/srv1/world-restore/snapshots",
        headers=_auth(),
        json=selection.model_dump(),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["snapshot"]["id"]
    assert len(data["snapshot"]["id"]) == 64


@pytest.mark.asyncio
async def test_create_snapshot_returns_423_when_locked(
    http: AsyncClient, lock
):
    selection = RestorationSelection(type=RestorationType.WORLD)
    holder = LockHolder(
        kind=ServerOperationKind.RESTORE,
        started_at=datetime.now(timezone.utc),
        user_id=42,
        description="held by test",
    )
    async with lock.acquire("srv1", holder):
        response = await http.post(
            "/api/servers/srv1/world-restore/snapshots",
            headers=_auth(),
            json=selection.model_dump(),
        )
    assert response.status_code == 423
    detail = response.json()["detail"]
    assert detail["reason"] == "locked"
    assert detail["holder"]["kind"] == "restore"


# --- Preview ---------------------------------------------------------------


@pytest.mark.skipif(not _mcmap_available(), reason="mcmap not installed")
@pytest.mark.asyncio
async def test_preview_sse_stream_emits_ready(
    http: AsyncClient, orchestrator
):
    # Use DIMENSION scope: it stages from restic but skips the mcmap render
    # step, so the test does not need a fully initialized live-map palette.
    # Region/chunk-scope rendering is exercised separately where the palette
    # can be wired up.
    selection = RestorationSelection(
        type=RestorationType.DIMENSION,
        region_dir_relpath="world/region",
    )
    snap = await orchestrator.create_snapshot("srv1", selection, user_id=None)

    response = await http.post(
        "/api/servers/srv1/world-restore/preview",
        headers=_auth(),
        json={
            "source_snapshot_id": snap.id,
            "selection": selection.model_dump(),
        },
    )
    assert response.status_code == 200
    events = _parse_sse_lines(response.text)
    types = [e["event_type"] for e in events]
    assert types[0] == "start"
    assert "ready" in types
    session_id = next(e["session_id"] for e in events if e.get("session_id"))
    await http.delete(
        f"/api/servers/srv1/world-restore/preview/{session_id}", headers=_auth()
    )


@pytest.mark.asyncio
async def test_preview_heartbeat_and_delete(
    http: AsyncClient, orchestrator
):
    session_dir = orchestrator._preview_manager.create_session("srv1")
    sid = session_dir.name

    r = await http.post(
        f"/api/servers/srv1/world-restore/preview/{sid}/heartbeat", headers=_auth()
    )
    assert r.status_code == 204

    r = await http.post(
        "/api/servers/srv1/world-restore/preview/unknown/heartbeat",
        headers=_auth(),
    )
    assert r.status_code == 404

    r = await http.delete(
        f"/api/servers/srv1/world-restore/preview/{sid}", headers=_auth()
    )
    assert r.status_code == 204

    # Idempotent — deleting again still 204.
    r = await http.delete(
        f"/api/servers/srv1/world-restore/preview/{sid}", headers=_auth()
    )
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_preview_tile_404_when_missing(
    http: AsyncClient, orchestrator
):
    session_dir = orchestrator._preview_manager.create_session("srv1")
    sid = session_dir.name
    r = await http.get(
        f"/api/servers/srv1/world-restore/preview/{sid}/tile/0/0.png",
        headers=_auth(),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_preview_tile_serves_png_when_present(
    http: AsyncClient, orchestrator
):
    session_dir = orchestrator._preview_manager.create_session("srv1")
    sid = session_dir.name
    tiles = session_dir / "tiles"
    tiles.mkdir()
    (tiles / "r.0.0.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    r = await http.get(
        f"/api/servers/srv1/world-restore/preview/{sid}/tile/0/0.png",
        headers=_auth(),
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


# --- Restoration -----------------------------------------------------------


@pytest.mark.asyncio
async def test_restore_409_when_server_running(
    http: AsyncClient, orchestrator, fake_instance
):
    selection = RestorationSelection(type=RestorationType.WORLD)
    snap = await orchestrator.create_snapshot("srv1", selection, user_id=None)
    fake_instance.set_status(MCServerStatus.RUNNING)
    r = await http.post(
        "/api/servers/srv1/world-restore/restore",
        headers=_auth(),
        json={"source_snapshot_id": snap.id, "selection": selection.model_dump()},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["reason"] == "server_running"


@pytest.mark.asyncio
async def test_restore_423_when_locked(
    http: AsyncClient, orchestrator, lock
):
    selection = RestorationSelection(type=RestorationType.WORLD)
    snap = await orchestrator.create_snapshot("srv1", selection, user_id=None)

    holder = LockHolder(
        kind=ServerOperationKind.BACKUP,
        started_at=datetime.now(timezone.utc),
        user_id=None,
        description="held by test",
    )
    async with lock.acquire("srv1", holder):
        r = await http.post(
            "/api/servers/srv1/world-restore/restore",
            headers=_auth(),
            json={
                "source_snapshot_id": snap.id,
                "selection": selection.model_dump(),
            },
        )
    assert r.status_code == 423
    assert r.json()["detail"]["reason"] == "locked"


@pytest.mark.asyncio
async def test_restore_sse_completes_and_writes_row(
    http: AsyncClient, orchestrator, session_factory, data_path
):
    selection = RestorationSelection(type=RestorationType.WORLD)
    snap = await orchestrator.create_snapshot("srv1", selection, user_id=None)
    (data_path / "world" / "region" / "r.0.0.mca").write_bytes(b"corrupt")

    r = await http.post(
        "/api/servers/srv1/world-restore/restore",
        headers=_auth(),
        json={
            "source_snapshot_id": snap.id,
            "selection": selection.model_dump(),
        },
    )
    assert r.status_code == 200
    events = _parse_sse_lines(r.text)
    assert events[0]["event_type"] == "start"
    assert events[-1]["event_type"] == "complete"
    rid = events[0]["restoration_id"]
    async with session_factory() as session:
        from sqlalchemy import select

        row = (
            await session.execute(
                select(Restoration).where(Restoration.id == rid)
            )
        ).scalar_one()
        assert row.status is RestorationStatus.SUCCEEDED


# --- Restoration history ---------------------------------------------------


@pytest.mark.asyncio
async def test_list_and_get_restorations(
    http: AsyncClient, orchestrator
):
    selection = RestorationSelection(type=RestorationType.WORLD)
    snap = await orchestrator.create_snapshot("srv1", selection, user_id=None)

    async for _ in orchestrator.begin_restore(
        server_id="srv1",
        source_snapshot_id=snap.id,
        selection=selection,
        user_id=99,
    ):
        pass

    r = await http.get(
        "/api/servers/srv1/world-restore/restorations",
        headers=_auth(),
        params={"limit": 10},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    rid = data["restorations"][0]["id"]

    r2 = await http.get(
        f"/api/servers/srv1/world-restore/restorations/{rid}", headers=_auth()
    )
    assert r2.status_code == 200
    assert r2.json()["id"] == rid
    assert r2.json()["initiated_by_user_id"] == 99


@pytest.mark.asyncio
async def test_rollback_creates_new_row(
    http: AsyncClient, orchestrator, data_path
):
    selection = RestorationSelection(type=RestorationType.WORLD)
    snap = await orchestrator.create_snapshot("srv1", selection, user_id=None)

    (data_path / "world" / "region" / "r.0.0.mca").write_bytes(b"pre-restore")

    rid = None
    async for ev in orchestrator.begin_restore(
        server_id="srv1",
        source_snapshot_id=snap.id,
        selection=selection,
        user_id=None,
    ):
        if ev.event_type == "start":
            rid = ev.restoration_id
    assert rid is not None

    r = await http.post(
        f"/api/servers/srv1/world-restore/restorations/{rid}/rollback",
        headers=_auth(),
    )
    assert r.status_code == 200
    events = _parse_sse_lines(r.text)
    assert events[-1]["event_type"] == "complete"
    assert (
        data_path / "world" / "region" / "r.0.0.mca"
    ).read_bytes() == b"pre-restore"


@pytest.mark.asyncio
async def test_rollback_404_when_not_found(http: AsyncClient):
    r = await http.post(
        "/api/servers/srv1/world-restore/restorations/deadbeef/rollback",
        headers=_auth(),
    )
    assert r.status_code == 404


# --- Validation guardrails -------------------------------------------------


@pytest.mark.asyncio
async def test_list_restorations_validates_pagination(http: AsyncClient):
    r = await http.get(
        "/api/servers/srv1/world-restore/restorations",
        headers=_auth(),
        params={"limit": 0},
    )
    assert r.status_code == 400
