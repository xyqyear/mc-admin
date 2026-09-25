import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.db.metadata import Base
from app.files.application import FileApplication
from app.mcmap import runner
from app.mcmap.cache import ServerMapCache
from app.mcmap.ownership import PreviewRenderTarget
from app.mcmap.queue import ServerRenderQueue
from app.minecraft import MCInstance, MCServerStatus
from app.operations.coordinator import (
    ResourceClaim,
    ResourceKind,
    get_operation_coordinator,
)
from app.operations.journal import OperationJournal
from app.operations.journal_types import OperationState, ResourceReference
from app.routers.servers import map as map_router
from app.servers.models import Server
from app.world.locks import LockHolder, ServerOperationKind, get_server_operation_lock
from app.world.preview import PreviewMapCache
from tests.support.runtime import set_runtime_resource


@pytest.fixture
async def map_application(isolated_runtime, monkeypatch, tmp_path):
    async with isolated_runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with isolated_runtime.database.session_factory() as session:
        session.add(Server(id=1, server_id="maps"))
        await session.commit()
    instance = MCInstance(isolated_runtime.settings.server_path, "maps")
    cache = ServerMapCache(instance.get_data_path())
    for region in ("world/region", "world/DIM-1/region"):
        mca = cache.mca_path(region, 0, 0)
        mca.parent.mkdir(parents=True)
        mca.write_bytes(b"original-mca")
    (cache.data_path / "server.properties").write_text("level-name=world\n")
    (cache.data_path / "world/level.dat").write_bytes(b"level")
    (instance.get_project_path() / "docker-compose.yml").write_text("services: {}\n")
    await cache.ensure_dir(cache.cache_dir)
    cache.client_jar.write_bytes(b"client")
    cache.palette_json.write_text("{}")
    monkeypatch.setattr(instance, "get_status", AsyncMock(return_value=MCServerStatus.CREATED))
    monkeypatch.setattr(instance, "get_compose_obj", AsyncMock(return_value=SimpleNamespace(get_game_version=lambda: "1.20.1")))
    journal = OperationJournal(isolated_runtime.database.session_factory)
    isolated_runtime.journal = journal
    manager = SimpleNamespace(servers_path=isolated_runtime.settings.server_path, get_instance=lambda _: instance, get_all_instances=AsyncMock(return_value=[instance]))
    set_runtime_resource(monkeypatch, 'docker_mc_manager', manager)
    set_runtime_resource(monkeypatch, 'dynamic_configuration', SimpleNamespace(mcmap=SimpleNamespace(batch_size=1, thread_count=1)))
    executable = tmp_path / "owned-renderer"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys, time\n"
        "from pathlib import Path\n"
        "out = Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "(out / 'r.0.0.png').write_bytes(b'partial-png')\n"
        "(out / 'ready').write_text(str(os.getpid()))\n"
        "while not (out / 'release').exists(): time.sleep(0.005)\n"
        "(out / 'r.0.0.png').write_bytes(b'complete-png')\n"
        "print(json.dumps(dict(type='region', x=0, z=0, status='rendered')), flush=True)\n"
    )
    executable.chmod(0o700)
    monkeypatch.setattr(runner.get_settings(), "mcmap_binary_path", executable)
    queues: list[ServerRenderQueue] = []

    def queue(region="world/region"):
        item = ServerRenderQueue("maps", region, cache)
        queues.append(item)
        return item

    yield SimpleNamespace(cache=cache, instance=instance, manager=manager, journal=journal, queue=queue)
    await asyncio.gather(*(queue.close() for queue in queues))


async def ready(path: Path) -> int:
    async with asyncio.timeout(5):
        while not path.exists():
            await asyncio.sleep(0.005)
        return int(path.read_text())


def holder():
    return LockHolder(ServerOperationKind.RESTORE, datetime.now(UTC), 0, "cache ownership test")


async def test_render_cancel_drains_real_child_before_world_cache_lease(map_application):
    app = map_application
    queue = app.queue()
    render = asyncio.create_task(queue.request(0, 0))
    tiles = app.cache.tiles_dir("world/region")
    pid = await ready(tiles / "ready")
    assert not get_server_operation_lock().is_locked("maps")
    attempted, acquired = asyncio.Event(), asyncio.Event()

    async def maintenance():
        attempted.set()
        async with get_server_operation_lock().lease(["maps"], holder(), claims=[ResourceClaim(ResourceKind.MAP_CACHE, "maps")]):
            acquired.set()
            assert not Path(f"/proc/{pid}").exists()
            assert not (tiles / "r.0.0.png").exists()

    waiting = asyncio.create_task(maintenance())
    try:
        await attempted.wait()
        assert not acquired.is_set()
        render.cancel()
        with pytest.raises(asyncio.CancelledError):
            await render
        await asyncio.wait_for(waiting, 5)
    finally:
        render.cancel()
        waiting.cancel()
        await asyncio.gather(render, waiting, return_exceptions=True)
    records = await app.journal.list()
    assert len(records) == 1
    assert records[0].state == OperationState.CANCELLED
    assert records[0].writers_stopped and not records[0].processes
    assert set(records[0].resources) == {ResourceReference("cache", "maps", 1, "world/region"), ResourceReference("files", "maps", 1, "data/.mcmap/tiles/world/region")}


async def test_independent_dimensions_render_concurrently_and_publish_after_child_exit(map_application):
    app = map_application
    regions = ["world/region", "world/DIM-1/region"]
    requests = [asyncio.create_task(app.queue(region).request(0, 0)) for region in regions]
    try:
        pids = await asyncio.gather(*(ready(app.cache.tiles_dir(region) / "ready") for region in regions))
        assert len(set(pids)) == 2
        assert all(not request.done() for request in requests)
        assert not get_operation_coordinator().is_occupied(ResourceClaim(ResourceKind.MAINTENANCE, "maps"))
        for region in regions:
            (app.cache.tiles_dir(region) / "release").touch()
        paths = await asyncio.wait_for(asyncio.gather(*requests), 5)
        assert all(path.read_bytes() == b"complete-png" for path in paths)
        assert all(not Path(f"/proc/{pid}").exists() for pid in pids)
    finally:
        for request in requests:
            request.cancel()
        await asyncio.gather(*requests, return_exceptions=True)
    assert all(record.state == OperationState.SUCCEEDED and record.writers_stopped for record in await app.journal.list())


async def test_render_file_scope_blocks_cache_edit_but_preserves_online_config_edit(map_application):
    app = map_application
    request = asyncio.create_task(app.queue().request(0, 0))
    tiles = app.cache.tiles_dir("world/region")
    try:
        await ready(tiles / "ready")
        files = FileApplication(app.instance, "maps", 0)
        with pytest.raises(HTTPException) as conflict:
            await files.update(".mcmap/tiles/world/region/r.0.0.png", "conflicting-edit")
        assert conflict.value.status_code == 423
        assert (tiles / "r.0.0.png").read_bytes() == b"partial-png"
        await files.update("server.properties", "level-name=world\nmotd=online edit\n")
        assert "online edit" in (app.cache.data_path / "server.properties").read_text()
        assert not request.done()
        (tiles / "release").touch()
        assert (await asyncio.wait_for(request, 5)).read_bytes() == b"complete-png"
    finally:
        request.cancel()
        await asyncio.gather(request, return_exceptions=True)


async def test_cancelled_render_waiter_does_not_spawn_after_world_lease(map_application, monkeypatch):
    app = map_application
    started = asyncio.Event()
    original = app.journal.start

    async def start(operation_id):
        result = await original(operation_id)
        started.set()
        return result

    monkeypatch.setattr(app.journal, "start", start)
    queue = app.queue()
    async with get_server_operation_lock().lease(["maps"], holder(), claims=[ResourceClaim(ResourceKind.MAP_CACHE, "maps")]):
        render = asyncio.create_task(queue.request(0, 0))
        await asyncio.wait_for(started.wait(), 5)
        render.cancel()
        with pytest.raises(asyncio.CancelledError):
            await render
        await asyncio.wait_for(queue.close(), 5)
        assert not app.cache.tiles_dir("world/region").exists()
    records = await app.journal.list()
    assert len(records) == 1 and records[0].state == OperationState.CANCELLED
    assert records[0].writers_stopped and not records[0].data_changed


async def test_palette_initialization_waits_for_renderer_without_clearing_files(map_application, monkeypatch):
    app = map_application
    monkeypatch.setattr(map_router, "discover_mods_dir", AsyncMock(return_value=None))
    monkeypatch.setattr(map_router, "palette_is_current", AsyncMock(return_value=True))
    started = asyncio.Event()
    original = app.journal.start

    async def start(operation_id):
        result = await original(operation_id)
        started.set()
        return result

    monkeypatch.setattr(app.journal, "start", start)

    async def initialize():
        return [json.loads(chunk.decode().removeprefix("data: ")) async for chunk in map_router._initialize_stream("maps")]

    async with get_operation_coordinator().acquire([ResourceClaim(ResourceKind.MAP_CACHE, "maps", "world/region")]):
        initialization = asyncio.create_task(initialize())
        await asyncio.wait_for(started.wait(), 5)
        assert not initialization.done()
        assert app.cache.palette_json.read_text() == "{}"
        assert not app.cache.palette_hash_file.exists()
    events = await asyncio.wait_for(initialization, 5)
    assert events[-1] == {"stage": "complete"}
    record = (await app.journal.list())[0]
    assert record.kind == "map_initialize" and record.state == OperationState.SUCCEEDED
    assert set(record.resources) == {ResourceReference("cache", "maps", 1), ResourceReference("files", "maps", 1, "data/.mcmap")}


def preview_queue(app, tmp_path, *, generation=1):
    session_id = "a" * 32
    session_dir = tmp_path / "preview" / session_id
    staged = session_dir / "source" / "world" / "region"
    staged.mkdir(parents=True)
    (staged / "r.0.0.mca").write_bytes(b"staged-mca")
    cache = PreviewMapCache(app.cache.palette_json, app.cache.data_path, staged, session_dir / "tiles")
    target = PreviewRenderTarget("maps", generation, session_id, session_dir)
    queue = ServerRenderQueue(session_id, "world/region", cast(ServerMapCache, cache), preview_target=target)
    return queue, target


@pytest.mark.parametrize("unknown_writer", [False, True])
async def test_preview_cancel_retains_correct_artifact_until_writer_ownership_is_confirmed(map_application, tmp_path, unknown_writer):
    app = map_application
    queue, target = preview_queue(app, tmp_path)
    live = app.cache.png_path("world/region", 0, 0)
    live.parent.mkdir(parents=True)
    live.write_bytes(b"live-cache-unchanged")
    request = asyncio.create_task(queue.request(0, 0))
    tiles = target.session_dir / "tiles"
    try:
        pid = await ready(tiles / "ready")
        record = (await app.journal.list())[0]
        assert record.kind == "world_preview_render" and len(record.processes) == 1
        assert {resource.server_id for resource in record.resources} == {"maps"}
        assert {resource.path for resource in record.resources if resource.kind == "files"} == {"data/.mcmap/palette.json"}
        assert any(reference.kind == "world_preview" and reference.value == target.session_id and not reference.resolved for reference in record.recovery_refs)
        if unknown_writer:
            await app.journal.set_ownership_known(record.operation_id, False)
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
    finally:
        request.cancel()
        await asyncio.gather(request, return_exceptions=True)
        await queue.close()
    assert not Path(f"/proc/{pid}").exists()
    record = (await app.journal.list())[0]
    assert record.writers_stopped is not unknown_writer
    assert all(reference.resolved is not unknown_writer for reference in record.recovery_refs)
    assert (tiles / "r.0.0.png").exists() is unknown_writer
    assert live.read_bytes() == b"live-cache-unchanged"
    if unknown_writer:
        await app.journal.resolve(record.operation_id, actor_id=0, writers_stopped=True, resolve_references=True)


async def test_preview_rejects_old_generation_before_spawning_a_renderer(map_application, tmp_path):
    app = map_application
    queue, target = preview_queue(app, tmp_path, generation=99)
    try:
        with pytest.raises(HTTPException) as conflict:
            await asyncio.wait_for(queue.request(0, 0), 5)
        assert conflict.value.status_code == 409
        assert not (target.session_dir / "tiles").exists()
    finally:
        await queue.close()
    record = (await app.journal.list())[0]
    assert record.state == OperationState.FAILED and record.writers_stopped and not record.data_changed
    assert not record.processes
