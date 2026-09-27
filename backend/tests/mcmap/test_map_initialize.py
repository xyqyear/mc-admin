from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.auth.schemas import UserPublic
from app.background_tasks import get_task_manager
from app.dependencies import get_current_user
from app.mcmap import initialization
from app.mcmap.cache import ServerMapCache
from app.mcmap.events import (
    MCMapDownloadClientResultEvent,
    MCMapErrorEvent,
    MCMapGenPaletteResultEvent,
)
from app.mcmap.palette import write_palette_hash
from app.routers.servers import map as map_router
from tests.support.runtime import set_runtime_resource

pytestmark = [pytest.mark.binary('fd')]


class _FakeCompose:
    def get_game_version(self) -> str:
        return "1.20.1"


class _FakeInstance:
    def __init__(self, data_path: Path) -> None:
        self._data_path = data_path

    def get_data_path(self) -> Path:
        return self._data_path

    async def exists(self) -> bool:
        return True

    async def get_compose_obj(self) -> _FakeCompose:
        return _FakeCompose()


class _FakeDockerMC:
    def __init__(self, instance: _FakeInstance) -> None:
        self._instance = instance

    def get_instance(self, server_id: str) -> _FakeInstance:
        return self._instance


class _FakeProc:
    def __init__(self, events: list[object]) -> None:
        self._events = events
        self.returncode = 0

    async def events(self, _adapter):
        for event in self._events:
            yield event

    async def stderr(self) -> str:
        return ""


@pytest.mark.asyncio
async def test_initialize_stream_force_rebuilds_current_prerequisites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_path = tmp_path / "data"
    cache = ServerMapCache(data_path=data_path)
    await cache.ensure_dir(cache.cache_dir)
    cache.client_jar.write_text("old-client")
    cache.palette_json.write_text("old-palette")
    await write_palette_hash(cache, "1.20.1", None)

    calls: list[str] = []
    fake_instance = _FakeInstance(data_path)
    set_runtime_resource(monkeypatch, 'docker_mc_manager', _FakeDockerMC(fake_instance))

    @asynccontextmanager
    async def fake_download_client(
        version: str, target: Path, *, owned_by: Path
    ) -> AsyncGenerator[_FakeProc]:
        assert not cache.client_jar.exists()
        assert not cache.palette_json.exists()
        assert not cache.palette_hash_file.exists()
        calls.append(f"download:{version}:{target.name}:{owned_by.name}")
        target.write_text("new-client")
        yield _FakeProc(
            [
                MCMapDownloadClientResultEvent(
                    type="result",
                    version=version,
                    target=str(target),
                    bytes=10,
                    sha1="abc",
                    move_method="rename",
                )
            ]
        )

    @asynccontextmanager
    async def fake_gen_palette(
        packs: list[Path],
        output: Path,
        *,
        level_dat: Path | None,
        owned_by: Path,
    ) -> AsyncGenerator[_FakeProc]:
        assert not cache.palette_json.exists()
        assert not cache.palette_hash_file.exists()
        calls.append(
            f"palette:{','.join(p.name for p in packs)}:{output.name}:{level_dat}:{owned_by.name}"
        )
        output.write_text("new-palette")
        yield _FakeProc(
            [
                MCMapGenPaletteResultEvent(
                    type="result",
                    output=str(output),
                    entries=1,
                    counters={},
                )
            ]
        )

    monkeypatch.setattr(initialization.mcmap_runner, "download_client", fake_download_client)
    monkeypatch.setattr(initialization.mcmap_runner, "gen_palette", fake_gen_palette)

    events = [event.model_dump(exclude_none=True) async for event in initialization.initialize_events("server-1", force=True)]

    assert calls == [
        f"download:1.20.1:client.jar:{data_path.name}",
        f"palette:client.jar:palette.json:None:{data_path.name}",
    ]
    assert cache.client_jar.read_text() == "new-client"
    assert cache.palette_json.read_text() == "new-palette"
    assert cache.palette_hash_file.read_text().strip()
    assert {"stage": "client", "phase": "done", "percent": 100, "cached": False} in events
    assert {
        "stage": "palette",
        "phase": "done",
        "percent": 100,
        "cached": False,
    } in events
    assert events[-1] == {"stage": "complete"}


@pytest.mark.parametrize("failure", [
    "compose_exception", "cleanup_exception",
    "client_exception", "client_event", "client_stderr",
    "palette_exception", "palette_event", "palette_stderr",
])
async def test_initialization_task_and_logs_do_not_expose_adapter_secrets(tmp_path, monkeypatch, caplog, failure):
    secret = "synthetic-map-secret-27d9d1"
    raw = f"password={secret}; INSERT INTO credentials VALUES ('{secret}')"
    cache = ServerMapCache(tmp_path / "data")
    await cache.ensure_dir(cache.cache_dir)
    instance = _FakeInstance(cache.data_path)
    set_runtime_resource(monkeypatch, 'docker_mc_manager', _FakeDockerMC(instance))
    monkeypatch.setattr(initialization, "discover_mods_dir", AsyncMock(return_value=None))
    monkeypatch.setattr(initialization, "discover_level_dat", AsyncMock(return_value=None))
    monkeypatch.setattr(initialization, "palette_is_current", AsyncMock(return_value=False))
    if failure.startswith("palette"):
        cache.client_jar.write_bytes(b"client")
    elif failure == "compose_exception":
        monkeypatch.setattr(instance, "get_compose_obj", AsyncMock(side_effect=RuntimeError(raw)))
    elif failure == "cleanup_exception":
        monkeypatch.setattr(initialization, "_clear_prerequisite_cache", AsyncMock(side_effect=OSError(raw)))

    @asynccontextmanager
    async def failing_adapter(*args, **kwargs):
        if failure.endswith("exception"):
            raise RuntimeError(raw)
        events: list[object] = [MCMapErrorEvent(type="error", message=raw)] if failure.endswith("event") else []
        process = _FakeProc(events)
        process.returncode = 0 if events else 1
        monkeypatch.setattr(process, "stderr", AsyncMock(return_value=raw))
        yield process

    monkeypatch.setattr(initialization.mcmap_runner, "download_client", failing_adapter)
    monkeypatch.setattr(initialization.mcmap_runner, "gen_palette", failing_adapter)
    application = FastAPI()
    application.include_router(map_router.router)
    application.dependency_overrides[get_current_user] = lambda: UserPublic(id=1, username="map-user", created_at=datetime.now(UTC))
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        response = await client.post("/servers/server-1/map/initialize", params={"force": failure == "cleanup_exception"})
        assert response.status_code == 202
        task_id = response.json()["task_id"]
        future = get_task_manager().get_future(task_id)
        assert future is not None
        result = await future
        assert not result.success
        task = get_task_manager().get_task(task_id)
        assert task is not None and task.error
        assert secret not in task.model_dump_json()
        if failure == "compose_exception":
            status = await client.get("/servers/server-1/map/status")
            assert status.status_code == 200 and status.json()["version"] is None
            assert secret not in status.text
    assert caplog.records
    assert secret not in caplog.text
    assert "INSERT INTO credentials" not in caplog.text
