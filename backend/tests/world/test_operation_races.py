import asyncio
from contextlib import aclosing, asynccontextmanager, suppress
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.background_tasks import BackgroundTaskManager, TaskProgress, TaskType
from app.configuration import application
from app.configuration.preparation import ServerConfiguration
from app.cron.jobs import restart
from app.cron.models import ExecutionStatus
from app.cron.types import ExecutionContext
from app.db.metadata import Base
from app.dynamic_config import get_config
from app.minecraft import MCServerStatus
from app.operation_admission import get_server_write_admission
from app.servers.lifecycle import orchestrators, primitives
from app.servers.models import Server
from app.world import locks
from tests.support.runtime import set_runtime_resource

COMPOSE = '''services:
  mc:
    container_name: mc-race
    image: itzg/minecraft-server:latest
    environment:
      VERSION: "1.21.8"
      MEMORY: "2G"
    ports:
      - "25565:25565"
      - "25575:25575"
'''
REBUILT_COMPOSE = COMPOSE.replace('MEMORY: "2G"', 'MEMORY: "3G"')


@pytest.fixture
def operation_lock(monkeypatch):
    lock = locks.ServerOperationLock()
    set_runtime_resource(monkeypatch, 'server_operation_lock', lock)
    return lock


@pytest.fixture
async def instance(isolated_runtime, monkeypatch):
    async with isolated_runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with isolated_runtime.database.session_factory() as session:
        session.add(Server(server_id="race"))
        await session.commit()
    project = isolated_runtime.settings.server_path / "race"
    project.mkdir()
    (project / "data").mkdir()
    (project / "docker-compose.yml").write_text(COMPOSE)
    instance = SimpleNamespace(
        get_project_path=Mock(return_value=project),
        exists=AsyncMock(return_value=True),
        created=AsyncMock(return_value=False),
        running=AsyncMock(return_value=True),
        get_status=AsyncMock(return_value=MCServerStatus.RUNNING),
        down=AsyncMock(), up=AsyncMock(), restart=AsyncMock(),
        remove=AsyncMock(),
    )
    manager = SimpleNamespace(
        get_instance=Mock(return_value=instance),
        servers_path=isolated_runtime.settings.server_path,
    )
    set_runtime_resource(monkeypatch, 'docker_mc_manager', manager)
    monkeypatch.setattr(application, "check_port_conflicts", AsyncMock(return_value=[]))
    return instance


def restart_context():
    return ExecutionContext(
        cronjob_id="restart", identifier="restart_server", execution_id="run",
        params=restart.ServerRestartParams(server_id="race"), started_at=datetime.now(UTC),
    )


@pytest.mark.parametrize("kind", [locks.ServerOperationKind.RESTORE, locks.ServerOperationKind.PRUNE])
async def test_rebuild_and_cron_cannot_enter_maintenance(operation_lock, instance, kind):
    entered, release = asyncio.Event(), asyncio.Event()

    async def maintenance():
        holder = locks.LockHolder(kind, datetime.now(UTC), None, "maintenance")
        async with operation_lock.acquire("race", holder):
            entered.set()
            await release.wait()

    task = asyncio.create_task(maintenance())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        with pytest.raises(HTTPException) as rejected:
            application.check_rebuild_available("race")
        assert rejected.value.status_code == 423
        async with aclosing(application.rebuild_server_task("race", ServerConfiguration(REBUILT_COMPOSE))) as events:
            with pytest.raises(HTTPException) as rejected:
                await anext(events)
            assert rejected.value.status_code == 423
        context = restart_context()
        await restart.restart_server_cronjob(context)
        assert context.status == ExecutionStatus.SKIPPED
        assert "维护" in context.messages[-1]
        instance.down.assert_not_awaited()
        assert (instance.get_project_path() / "docker-compose.yml").read_bytes() == COMPOSE.encode()
        instance.restart.assert_not_awaited()
    finally:
        release.set()
        await task


@pytest.mark.parametrize("operation", ["rebuild", "cron"])
async def test_starting_operation_owns_lock_until_docker_returns(operation_lock, instance, operation):
    entered, release = asyncio.Event(), asyncio.Event()

    async def block():
        entered.set()
        await release.wait()

    if operation == "rebuild":
        instance.down.side_effect = block
    else:
        instance.restart.side_effect = block

    async def run():
        if operation == "rebuild":
            async with aclosing(application.rebuild_server_task("race", ServerConfiguration(REBUILT_COMPOSE))) as events:
                async for _ in events:
                    pass
        else:
            await restart.restart_server_cronjob(restart_context())

    task = asyncio.create_task(run())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        assert (instance.get_project_path() / "docker-compose.yml").read_bytes() == COMPOSE.encode()
        for kind in (locks.ServerOperationKind.RESTORE, locks.ServerOperationKind.PRUNE):
            holder = locks.LockHolder(kind, datetime.now(UTC), None, "maintenance")
            async with operation_lock.try_acquire("race", holder) as acquired:
                assert not acquired
    finally:
        release.set()
        await task
    assert not operation_lock.is_locked("race")
    expected = REBUILT_COMPOSE if operation == "rebuild" else COMPOSE
    assert (instance.get_project_path() / "docker-compose.yml").read_bytes() == expected.encode()
    assert not list(instance.get_project_path().glob(".mc-admin-configuration-*.tmp"))


async def test_delete_timeout_preserves_files_and_freeze_rejects_new_writers(instance, monkeypatch, operation_lock):
    manager = BackgroundTaskManager()
    set_runtime_resource(monkeypatch, 'task_manager', manager)
    entered, release, deleting = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def writer():
        entered.set()
        try:
            await release.wait()
            yield TaskProgress(progress=100, message="done")
        finally:
            await release.wait()

    running = manager.submit(TaskType.ARCHIVE_EXTRACT, "writer", writer(), server_id="race")
    await entered.wait()

    async def drain(server_id):
        deleting.set()
        await asyncio.sleep(0)
        return await primitives.cancel_and_wait_for_tasks(server_id, timeout=0)

    monkeypatch.setattr(orchestrators, "cancel_and_wait_for_tasks", drain)
    metadata = AsyncMock()
    monkeypatch.setattr(orchestrators, "mark_server_removed", metadata)
    task = asyncio.create_task(orchestrators.remove_server_full(AsyncMock(), "race"))
    await deleting.wait()
    try:
        rejected_generator = writer()
        try:
            with pytest.raises(HTTPException) as rejected:
                manager.submit(TaskType.ARCHIVE_EXTRACT, "new", rejected_generator, server_id="race")
            assert rejected.value.status_code == 423
        finally:
            await rejected_generator.aclose()
        holder = locks.LockHolder(locks.ServerOperationKind.RESTORE, datetime.now(UTC), None, "restore")
        with pytest.raises(HTTPException):
            async with operation_lock.acquire("race", holder):
                pytest.fail("restore entered deletion")
        with pytest.raises(HTTPException) as failure:
            await task
        assert failure.value.status_code == 409
        metadata.assert_not_awaited()
        instance.remove.assert_not_awaited()
        assert (instance.get_project_path() / "docker-compose.yml").read_bytes() == COMPOSE.encode()
        assert not get_server_write_admission().is_frozen("race")
    finally:
        release.set()
        await running.awaitable


@pytest.mark.parametrize("writer_kind", ["restore", "file"])
async def test_delete_preserves_request_owned_writers(instance, monkeypatch, operation_lock, writer_kind):
    monkeypatch.setattr(orchestrators, "cancel_and_wait_for_tasks", AsyncMock(return_value=[]))
    metadata = AsyncMock()
    monkeypatch.setattr(orchestrators, "mark_server_removed", metadata)
    entered, release = asyncio.Event(), asyncio.Event()

    async def writer():
        if writer_kind == "restore":
            holder = locks.LockHolder(locks.ServerOperationKind.RESTORE, datetime.now(UTC), None, "restore")
            async with operation_lock.acquire("race", holder):
                entered.set()
                await release.wait()
        else:
            with get_server_write_admission().write(["race"]):
                entered.set()
                await release.wait()

    task = asyncio.create_task(writer())
    await entered.wait()
    try:
        with pytest.raises(HTTPException) as failure:
            await orchestrators.remove_server_full(AsyncMock(), "race")
        assert failure.value.status_code == 423
        metadata.assert_not_awaited()
        instance.remove.assert_not_awaited()
        assert (instance.get_project_path() / "docker-compose.yml").read_bytes() == COMPOSE.encode()
    finally:
        release.set()
        await task
    get_server_write_admission().require_drained("race")


async def test_map_worker_owns_write_until_cleanup_after_client_disconnect(tmp_path, monkeypatch):
    from app.mcmap import queue as queue_module
    from app.mcmap.cache import ServerMapCache

    entered, stopped = asyncio.Event(), asyncio.Event()
    cleaning, release = asyncio.Event(), asyncio.Event()

    async def events(_):
        entered.set()
        await stopped.wait()
        if False:
            yield

    async def terminate():
        stopped.set()

    @asynccontextmanager
    async def render(**_):
        try:
            yield SimpleNamespace(events=events, terminate=terminate)
        finally:
            cleaning.set()
            await release.wait()

    monkeypatch.setattr(queue_module.runner, "render", render)
    monkeypatch.setattr(get_config().mcmap, "batch_size", 1)
    monkeypatch.setattr(get_config().mcmap, "thread_count", 1)
    queue = queue_module.ServerRenderQueue("race", "world/region", ServerMapCache(tmp_path))
    request = asyncio.create_task(queue.request(0, 0))
    await asyncio.wait_for(entered.wait(), 5)
    request.cancel()
    with suppress(asyncio.CancelledError):
        await request
    await asyncio.wait_for(cleaning.wait(), 5)
    try:
        with get_server_write_admission().freeze("race"):
            with pytest.raises(HTTPException):
                get_server_write_admission().require_drained("race")
            with pytest.raises(HTTPException):
                await queue.request(1, 0)
    finally:
        release.set()
        worker = queue._worker_task
        assert worker is not None
        await asyncio.sleep(0)
        queue.shutdown()
        with suppress(asyncio.CancelledError):
            await worker
    get_server_write_admission().require_drained("race")
