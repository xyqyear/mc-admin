import asyncio
import io
from contextlib import aclosing
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, UploadFile

from app.archive import application as archives
from app.background_tasks import BackgroundTaskManager, TaskType
from app.db.metadata import Base
from app.files import multi_file, ownership
from app.files.application import FileApplication
from app.files.types import (
    CreateFileRequest,
    MultiFileUploadRequest,
    OverwritePolicy,
    RenameFileRequest,
)
from app.minecraft import MCInstance, MCServerStatus
from app.operation_admission import get_server_write_admission
from app.operations.coordinator import (
    ResourceClaim,
    ResourceKind,
    get_operation_coordinator,
)
from app.operations.journal import OperationJournal
from app.operations.journal_types import (
    OperationSpec,
    OperationState,
    RecoveryReference,
    ResourceReference,
)
from app.operations.recovery import RecoveryService
from app.servers.lifecycle import (
    CreateServerSpec,
    adopt_server_partial,
    create_server_full,
)
from app.servers.models import Server
from app.snapshots import ResticClient, SnapshotService
from app.snapshots.application import SnapshotApplication, SnapshotMaintenanceConflict
from app.snapshots.restore import SnapshotRestoreService
from app.utils.exec import exec_command
from app.world.locks import LockHolder, ServerOperationKind, get_server_operation_lock
from tests.support.runtime import set_runtime_resource


@pytest.fixture
async def file_application(isolated_runtime, monkeypatch):
    async with isolated_runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with isolated_runtime.database.session_factory() as session:
        session.add(Server(id=1, server_id="first"))
        await session.commit()
    instance = MCInstance(isolated_runtime.settings.server_path, "first")
    data = instance.get_data_path()
    (data / "world").mkdir(parents=True)
    (data / "world" / "level.dat").write_bytes(b"world-original")
    (data / "server.properties").write_text("level-name=world\n")
    (data / "plugin.conf").write_text("plugin-original")
    (instance.get_project_path() / "docker-compose.yml").write_text("services: {}\n")
    monkeypatch.setattr(instance, "get_status", AsyncMock(return_value=MCServerStatus.HEALTHY))
    manager = SimpleNamespace(servers_path=isolated_runtime.settings.server_path, get_all_instances=AsyncMock(return_value=[instance]), get_instance=lambda _: instance)
    journal = OperationJournal(isolated_runtime.database.session_factory)
    isolated_runtime.journal = journal
    tasks = BackgroundTaskManager(journal)
    isolated_runtime.resources["task_manager"] = tasks
    recovery = RecoveryService(journal, probe=AsyncMock(return_value=True), servers_root=isolated_runtime.settings.server_path, archive_root=isolated_runtime.settings.archive_path)
    isolated_runtime.resources["operation_recovery"] = recovery
    yield SimpleNamespace(application=FileApplication(instance, "first", 0), instance=instance, data=data, manager=manager, journal=journal, runtime=isolated_runtime, tasks=tasks, recovery=recovery)
    await tasks.shutdown()


def holder():
    return LockHolder(ServerOperationKind.RESTORE, datetime.now(UTC), 0, "owned test maintenance")


async def test_world_scope_blocks_overlapping_writes_but_allows_online_sibling_edits(file_application):
    app, data = file_application.application, file_application.data
    claims = [ResourceClaim(ResourceKind.FILES, "first", "data/world")]
    (data / "alias").symlink_to(data / "world", target_is_directory=True)
    async with get_server_operation_lock().lease(["first"], holder(), claims=claims):
        for path in ("world/level.dat", "alias/level.dat"):
            with pytest.raises(HTTPException) as conflict:
                await app.update(path, "cannot-write")
            assert conflict.value.status_code == 423
        with pytest.raises(HTTPException) as conflict:
            await app.delete("world")
        assert conflict.value.status_code == 423
        with pytest.raises(HTTPException):
            await app.rename(RenameFileRequest(old_path="world", new_name="world-renamed"))
        with pytest.raises(HTTPException):
            await app.create(CreateFileRequest(path="world", name="new.txt", type="file"))
        await app.update("plugin.conf", "online-change")
        assert (data / "world" / "level.dat").read_bytes() == b"world-original"
        assert (data / "plugin.conf").read_text() == "online-change"
    records = await file_application.journal.list()
    completed = next(record for record in records if record.state == OperationState.SUCCEEDED)
    assert completed.resources == (ResourceReference("files", "first", 1, "data/plugin.conf"),)


async def test_cancelled_world_file_restore_invalidates_cache_before_restic_file_events(file_application, monkeypatch):
    app = file_application
    monkeypatch.setattr(app.instance, "get_status", AsyncMock(return_value=MCServerStatus.CREATED))
    cache = app.data / ".mcmap" / "tiles"
    cache.mkdir(parents=True)
    (cache / "old.png").write_bytes(b"stale")
    entered = asyncio.Event()

    async def interrupted_restore(snapshot_id, paths):
        (app.data / "world" / "level.dat").write_bytes(b"partly-restored")
        entered.set()
        await asyncio.Event().wait()
        yield None

    snapshots = SnapshotService(ResticClient(str(app.runtime.scratch_dir / "unused-restic"), password="test"), app.manager)
    monkeypatch.setattr(snapshots, "create_snapshot", AsyncMock(return_value=SimpleNamespace(id="safety", short_id="safety")))
    monkeypatch.setattr(snapshots, "restore", interrupted_restore)
    service = SnapshotRestoreService(snapshots, app.manager, get_server_operation_lock())

    async def restore():
        return [event async for event in service.restore("original", [app.data / "world"], ["first"], 0)]

    request = asyncio.create_task(restore())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        assert get_operation_coordinator().is_occupied(ResourceClaim(ResourceKind.MAP_CACHE, "first"))
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
    finally:
        request.cancel()
        await asyncio.gather(request, return_exceptions=True)
    assert not cache.exists()
    assert (app.data / "world" / "level.dat").read_bytes() == b"partly-restored"
    record = (await app.journal.list())[0]
    assert record.state == OperationState.INTERRUPTED and record.writers_stopped
    assert ResourceReference("cache", "first", 1) in record.resources


async def test_upload_conflict_keeps_session_and_cancellation_preserves_finished_files(file_application, monkeypatch):
    app, data = file_application.application, file_application.data
    upload = await multi_file.check_upload_conflicts(data, "/", MultiFileUploadRequest(files=[]))
    await multi_file.set_upload_policy(upload.session_id, OverwritePolicy(mode="always_overwrite"))
    files = [UploadFile(filename="world/new.txt", file=io.BytesIO(b"first"))]
    async with get_server_operation_lock().lease(["first"], holder(), claims=[ResourceClaim(ResourceKind.FILES, "first", "data/world")]):
        with pytest.raises(HTTPException) as conflict:
            await app.upload(upload.session_id, "/", files)
        assert conflict.value.status_code == 423
        assert multi_file.require_upload_session(upload.session_id) is not None
        assert not (data / "world" / "new.txt").exists()

    entered, release = asyncio.Event(), asyncio.Event()
    original = multi_file._write_file

    async def write_then_pause(file, target, root):
        await original(file, target, root)
        entered.set()
        await release.wait()

    monkeypatch.setattr(multi_file, "_write_file", write_then_pause)
    files.append(UploadFile(filename="later.txt", file=io.BytesIO(b"second")))
    task = asyncio.create_task(app.upload(upload.session_id, "/", files))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        with pytest.raises(HTTPException):
            await app.delete("world")
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert (data / "world" / "new.txt").read_bytes() == b"first"
    assert not (data / "later.txt").exists()


async def test_ownership_task_holds_real_data_scope_until_external_command_finishes(file_application, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()

    async def chown(*args):
        entered.set()
        await release.wait()
        return ""

    monkeypatch.setattr(ownership, "exec_command", chown)
    app, data = file_application.application, file_application.data
    claims = await app.claims([data])
    submitted = await file_application.tasks.submit_durable(TaskType.FILE_OWNERSHIP_REPAIR, "ownership", app.task([data], ownership.restore_tree_ownership_task(data), claims=claims), server_id="first", claims=claims)
    try:
        await asyncio.wait_for(entered.wait(), 5)
        with pytest.raises(HTTPException) as conflict:
            await app.update("plugin.conf", "cannot-write")
        assert conflict.value.status_code == 423
    finally:
        release.set()
        assert (await submitted.awaitable).success
    await app.update("plugin.conf", "after-repair")


@pytest.mark.binary("restic")
async def test_real_online_restore_reuses_file_lease_and_preserves_ignored_paths(file_application, tmp_path, monkeypatch):
    client = ResticClient(str(tmp_path / "repo"), password="owned-test")
    await exec_command(str(client.binary_path), "init", env=client.env)
    snapshots = SnapshotService(client, file_application.manager)
    set_runtime_resource(monkeypatch, 'dynamic_configuration', SimpleNamespace(snapshots=SimpleNamespace(ignored_paths=["ignored"])))
    data = file_application.data
    snapshot = await snapshots.create_snapshot([data])
    (data / "plugin.conf").write_text("changed")
    (data / "ignored").mkdir()
    (data / "ignored" / "retained.txt").write_text("retain")
    application = SnapshotApplication(snapshots, file_application.manager, get_server_operation_lock())
    service = SnapshotRestoreService(snapshots, file_application.manager, get_server_operation_lock())
    async with get_server_operation_lock().lease(["first"], holder(), claims=[ResourceClaim(ResourceKind.FILES, "first", "data/world")]):
        with pytest.raises(SnapshotMaintenanceConflict):
            await application.backup([data])
        async with aclosing(service.restore(snapshot.id, [data / "plugin.conf"], [], 0)) as events:
            result = [event async for event in events]
        assert result[-1]["event_type"] == "complete"
        assert (data / "plugin.conf").read_text() == "plugin-original"
        assert (data / "ignored" / "retained.txt").read_text() == "retain"
        file_application.instance.get_status.assert_not_awaited()


@pytest.mark.parametrize("unknown_writer", [False, True])
async def test_archive_recovery_cleans_only_recorded_stage_after_writers_stop(file_application, unknown_writer):
    root = file_application.runtime.settings.archive_path
    token = "a" * 32
    own = root / f".mc-admin-archive-{token}.tmp"
    unrelated = root / f".mc-admin-archive-{'b' * 32}.tmp"
    own.write_bytes(b"owned")
    unrelated.write_bytes(b"keep")
    journal = file_application.journal
    await journal.accept(OperationSpec("archive_create", (ResourceReference("archive", path=own.name),), operation_id="staged"))
    await journal.start("staged")
    await journal.phase("staged", "compressing_archive", recovery_refs=(RecoveryReference("archive_stage", token),))
    if unknown_writer:
        await journal.set_ownership_known("staged", False)
        file_application.recovery.probe.return_value = False
        report = await file_application.recovery.recover()
        assert report.blocks and own.exists()
        file_application.recovery.probe.return_value = True
    else:
        await journal.finish("staged", OperationState.FAILED, writers_stopped=True)
        assert await journal.unsettled()
    await file_application.recovery.recover()
    assert not own.exists() and unrelated.read_bytes() == b"keep"
    record = await journal.get("staged")
    assert record is not None and all(reference.resolved for reference in record.recovery_refs)


async def test_global_file_scope_prevents_new_instance_creation_or_adoption(file_application):
    root = file_application.runtime.settings.server_path
    async with get_operation_coordinator().acquire([ResourceClaim(ResourceKind.FILES)]):
        async with file_application.runtime.database.session_factory() as session:
            with pytest.raises(HTTPException) as create:
                await create_server_full(session, "new", CreateServerSpec(yaml_content="services: {}"))
            assert create.value.status_code == 423
            with pytest.raises(HTTPException) as adopt:
                await adopt_server_partial(session, "orphan", game_port=25565, rcon_port=25575)
            assert adopt.value.status_code == 423
        assert not (root / "new").exists()
        with pytest.raises(HTTPException):
            await file_application.application.update("plugin.conf", "blocked")
    assert (file_application.data / "plugin.conf").read_text() == "plugin-original"
    await file_application.application.update("plugin.conf", "after-global-restore")


async def test_unknown_archive_writer_blocks_only_its_archive_scope(file_application):
    journal = file_application.journal
    await journal.accept(OperationSpec("archive_publish", (ResourceReference("archive", path="busy.zip"),), operation_id="busy-archive"))
    await journal.start("busy-archive")
    await journal.set_ownership_known("busy-archive", False)
    file_application.recovery.probe.return_value = False
    await file_application.recovery.recover()
    await file_application.recovery.apply_blocks(get_server_write_admission())
    archive = archives.ArchiveApplication(file_application.runtime.settings.archive_path)
    with pytest.raises(HTTPException) as conflict:
        await archive.create(CreateFileRequest(path="/", name="busy.zip", type="file"))
    assert conflict.value.status_code == 423
    await archive.create(CreateFileRequest(path="/", name="other.zip", type="file"))
    await file_application.application.update("plugin.conf", "unrelated")
    file_application.recovery.probe.return_value = True
    await file_application.recovery.recover()
    await file_application.recovery.apply_blocks(get_server_write_admission())
    await archive.create(CreateFileRequest(path="/", name="busy.zip", type="file"))


@pytest.mark.binary("7z")
async def test_real_compression_publishes_complete_output_after_owned_stage(file_application, monkeypatch):
    from app.routers.archive import list_archive_files

    entered, release = asyncio.Event(), asyncio.Event()
    original = archives.create_server_archive_stream

    async def compressed_stage(*args, **kwargs):
        async with aclosing(original(*args, **kwargs)) as events:
            async for event in events:
                if event.result is not None:
                    entered.set()
                    await release.wait()
                yield event

    monkeypatch.setattr(archives, "create_server_archive_stream", compressed_stage)
    plan = await archives.prepare_compression(file_application.instance, "/")
    submitted = await file_application.tasks.submit_durable(TaskType.ARCHIVE_CREATE, "compression", archives.compress(plan), server_id="first", claims=plan.claims)
    try:
        await asyncio.wait_for(entered.wait(), 10)
        assert plan.stage.is_file() and not plan.output.exists()
        assert not (await list_archive_files()).items
        with pytest.raises(HTTPException):
            await file_application.application.update("plugin.conf", "blocked")
        with pytest.raises(HTTPException):
            await archives.ArchiveApplication(plan.output.parent).delete(plan.output.name)
    finally:
        release.set()
        assert (await submitted.awaitable).success
    assert not plan.stage.exists() and plan.output.is_file()
    assert "plugin-original" in await exec_command("7z", "x", "-so", str(plan.output), "data/plugin.conf")
