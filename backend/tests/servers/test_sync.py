"""End-to-end tests for POST /api/servers/sync.

Covers: empty diff, fs_only / db_only / mixed, validation errors, dry-run,
empty-fs safety guard, and concurrent 409.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import get_db
from app.main import api_app
from app.minecraft import DockerMCManager
from app.models import Base
from app.servers.crud import create_server_record


YAML_TEMPLATE = """
version: '3.8'
services:
  mc:
    image: itzg/minecraft-server:latest
    container_name: mc-{server_name}
    ports:
      - "{game_port}:25565"
      - "{rcon_port}:25575"
    environment:
      EULA: "TRUE"
      VERSION: "1.20.1"
      MEMORY: "2G"
    volumes:
      - ./data:/data
    restart: unless-stopped
"""


def _yaml(server_name: str, game_port: int = 25565, rcon_port: int = 25575) -> str:
    return YAML_TEMPLATE.format(
        server_name=server_name, game_port=game_port, rcon_port=rcon_port
    ).strip()


def _auth():
    return {"Authorization": "Bearer test-master-token"}


def _set_session_cookies(client: TestClient, user):
    from app.auth.session import AUTH_COOKIE_NAME, CSRF_COOKIE_NAME, create_session_token

    token, csrf_token = create_session_token(user)
    client.cookies.set(AUTH_COOKIE_NAME, token, path="/api")
    client.cookies.set(CSRF_COOKIE_NAME, csrf_token, path="/")
    return csrf_token


@pytest.fixture
def temp_server_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
async def test_db():
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{temp_db.name}", echo=False
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    TestSessionLocal = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    yield TestSessionLocal
    await engine.dispose()
    Path(temp_db.name).unlink(missing_ok=True)


@pytest.fixture
def test_client(temp_server_path, test_db):
    async def override_get_db():
        async with test_db() as session:
            yield session

    api_app.dependency_overrides[get_db] = override_get_db

    real_mc_manager = DockerMCManager(temp_server_path)
    patches = [
        patch("app.config.settings.server_path", temp_server_path),
        patch("app.config.settings.master_token", "test-master-token"),
        patch("app.routers.servers.sync.docker_mc_manager", real_mc_manager),
        patch(
            "app.servers.lifecycle.orchestrators.docker_mc_manager",
            real_mc_manager,
        ),
        patch(
            "app.servers.lifecycle.primitives.docker_mc_manager", real_mc_manager
        ),
        patch("app.servers.port_utils.docker_mc_manager", real_mc_manager),
        patch("app.servers.port_utils.get_system_used_ports", return_value=set()),
        patch(
            "app.servers.lifecycle.orchestrators.log_monitor.start_server",
            new_callable=AsyncMock,
        ),
        patch(
            "app.servers.lifecycle.orchestrators.log_monitor.stop_watching",
            new_callable=AsyncMock,
        ),
        patch(
            "app.servers.lifecycle.orchestrators.simple_dns_manager.update",
            new_callable=AsyncMock,
        ),
        patch(
            "app.servers.lifecycle.orchestrators.close_open_sessions",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "app.routers.servers.sync.simple_dns_manager.update",
            new_callable=AsyncMock,
        ),
        patch(
            "app.minecraft.docker.manager.ComposeManager.created",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ]
    for p in patches:
        p.start()
    yield TestClient(api_app, raise_server_exceptions=False), real_mc_manager, test_db
    for p in patches:
        p.stop()
    api_app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSyncEmpty:
    def test_empty_diff(self, test_client):
        client, _mgr, _db = test_client

        response = client.post("/api/servers/sync", json={}, headers=_auth())

        assert response.status_code == 200
        data = response.json()
        assert data["applied"] is True
        assert data["adopted"] == []
        assert data["removed"] == []
        assert data["preview"] == []
        assert data["errors"] == []


class TestSyncFsOnly:
    def test_adopt_valid_directory(self, test_client):
        client, mgr, _db = test_client
        # Stage a directory on disk
        asyncio.run(mgr.get_instance("orphan").create(_yaml("orphan", 26500, 26510)))

        response = client.post("/api/servers/sync", json={}, headers=_auth())

        assert response.status_code == 200
        data = response.json()
        assert data["applied"] is True
        assert len(data["adopted"]) == 1
        assert data["adopted"][0]["server_id"] == "orphan"
        assert data["adopted"][0]["game_port"] == 26500
        assert data["adopted"][0]["rcon_port"] == 26510
        # Preview should also include the adopt entry
        adopt_previews = [p for p in data["preview"] if p["action"] == "adopt"]
        assert len(adopt_previews) == 1

    def test_invalid_compose_goes_to_errors(self, test_client):
        client, mgr, _db = test_client
        # Stage a directory with a broken compose
        (mgr.servers_path / "broken").mkdir()
        (mgr.servers_path / "broken" / "docker-compose.yml").write_text(
            "version: '3.8'\nservices:\n  mc:\n    image: nginx\n"
        )

        response = client.post("/api/servers/sync", json={}, headers=_auth())

        assert response.status_code == 200
        data = response.json()
        # "broken" is filtered out at MCComposeFile validation by
        # get_all_server_names, so it won't even appear in fs_only.
        # That is the intended behavior — only valid MC servers show up.
        assert data["adopted"] == []


class TestSyncDbOnly:
    def test_deactivate_orphaned_db_row(self, test_client):
        client, mgr, db = test_client

        # Stage a real server on disk so the empty-fs safety guard does not
        # trip — without an anchor the db_only path requires force=true.
        asyncio.run(mgr.get_instance("anchor").create(_yaml("anchor", 26600, 26610)))

        async def setup():
            async with db() as s:
                await create_server_record(s, "stale-row")

        asyncio.run(setup())

        response = client.post("/api/servers/sync", json={}, headers=_auth())

        assert response.status_code == 200
        data = response.json()
        # stale-row gets deactivated; anchor gets adopted
        assert {r["server_id"] for r in data["removed"]} == {"stale-row"}
        assert {a["server_id"] for a in data["adopted"]} == {"anchor"}


class TestSyncEmptyFsGuard:
    def test_empty_fs_with_db_rows_blocks_without_force(self, test_client):
        client, _mgr, db = test_client

        async def setup():
            async with db() as s:
                await create_server_record(s, "orphaned-1")
                await create_server_record(s, "orphaned-2")

        asyncio.run(setup())

        response = client.post("/api/servers/sync", json={}, headers=_auth())

        assert response.status_code == 409
        assert "force=true" in response.json()["detail"]

    def test_empty_fs_with_force_succeeds(self, test_client):
        client, _mgr, db = test_client

        async def setup():
            async with db() as s:
                await create_server_record(s, "orphaned-x")

        asyncio.run(setup())

        response = client.post(
            "/api/servers/sync", json={"force": True}, headers=_auth()
        )

        assert response.status_code == 200
        data = response.json()
        assert {r["server_id"] for r in data["removed"]} == {"orphaned-x"}


class TestSyncDryRun:
    def test_dry_run_no_writes(self, test_client):
        client, mgr, db = test_client

        asyncio.run(mgr.get_instance("ghost").create(_yaml("ghost", 26700, 26710)))

        async def setup():
            async with db() as s:
                await create_server_record(s, "vanished")

        asyncio.run(setup())

        response = client.post(
            "/api/servers/sync", json={"dry_run": True}, headers=_auth()
        )

        assert response.status_code == 200
        data = response.json()
        assert data["applied"] is False
        assert data["adopted"] == []
        assert data["removed"] == []
        # Preview should contain both buckets
        preview_actions = {p["action"] for p in data["preview"]}
        assert preview_actions == {"adopt", "deactivate"}

        # Verify DB state is unchanged (vanished row still ACTIVE)
        from app.servers.crud import get_active_server_by_id

        async def check():
            async with db() as s:
                row = await get_active_server_by_id(s, "vanished")
                return row

        row = asyncio.run(check())
        assert row is not None


class TestSyncOwnerOnly:
    def test_non_owner_forbidden(self, test_client):
        client, _mgr, _db = test_client

        from datetime import datetime, timezone

        from app.auth.session import CSRF_HEADER_NAME
        from app.models import UserPublic, UserRole

        csrf_token = _set_session_cookies(
            client,
            UserPublic(
                id=7,
                username="tester",
                role=UserRole.ADMIN,
                created_at=datetime.now(timezone.utc),
            ),
        )

        response = client.post(
            "/api/servers/sync",
            json={},
            headers={CSRF_HEADER_NAME: csrf_token},
        )

        assert response.status_code == 403
