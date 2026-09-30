"""Tests for PreviewSessionManager: create/heartbeat/end, janitor reaping,
disk guard, one-preview-per-server enforcement."""
import asyncio
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.dynamic_config import get_config
from app.dynamic_config.configs.snapshots import WorldRestoreConfig
from app.mcmap.queue import ServerRenderQueue
from app.snapshots.preview_sessions import (
    PreviewDiskGuardError,
    PreviewSessionManager,
    PreviewSessionNotFoundError,
)
from tests.support.runtime import set_runtime_resource

default_region_bytes = WorldRestoreConfig().preview_avg_region_bytes


async def test_ready_preview_keeps_source_until_expiry_and_active_readers_finish(manager):
    directory = await manager.create_session("srv1", source_snapshot_id="source")
    from app.world.artifacts import release_artifact

    await release_artifact("world_preview", directory.name)
    repository = manager._repository_use
    with pytest.raises(HTTPException), repository.maintain():
        pass
    async with manager.use(directory.name):
        manager._sessions[directory.name].last_seen -= timedelta(hours=1)
        assert await manager.reap_stale() == [directory.name]
        with pytest.raises(HTTPException), repository.maintain():
            pass
        assert directory.exists()
    assert not directory.exists()
    with repository.maintain():
        assert not repository.active_snapshots


async def test_concurrent_creates_keep_only_latest_session(manager):
    created = await asyncio.gather(*(manager.create_session("srv1") for _ in range(4)))
    active = manager.get_active_for_server("srv1")
    assert active in {path.name for path in created}
    assert [path.name for path in created if path.exists()] == [active]
    assert set(manager._sessions) == {active}


async def test_tile_read_keeps_reference_until_bytes_are_loaded(manager):
    from app.world.preview_rendering import WorldPreviewRenderer
    from app.world.scope_execution import RestoreScopeExecutor

    snapshots = AsyncMock()
    application = WorldPreviewRenderer(snapshots, RestoreScopeExecutor(snapshots), manager)
    directory = await manager.create_session("srv1")
    rendering = asyncio.Event()
    finish_rendering = asyncio.Event()
    png = directory / "tiles" / "r.0.0.png"
    png.parent.mkdir()

    async def render(_rx, _rz):
        rendering.set()
        await finish_rendering.wait()
        png.write_bytes(b"preview-png")
        return png

    queue = SimpleNamespace(request=render, close=AsyncMock())
    manager.attach_render_queue(directory.name, queue=cast(ServerRenderQueue, queue), affected_keys={(0, 0)})
    reading = asyncio.create_task(application.read_preview_tile(directory.name, 0, 0, timeout=5))
    await asyncio.wait_for(rendering.wait(), 5)
    await manager.end(directory.name)
    assert directory.exists()
    finish_rendering.set()
    assert await reading == b"preview-png"
    assert not directory.exists()


async def test_orphan_reaper_preserves_session_created_during_directory_listing(manager, monkeypatch):
    from app.snapshots import preview_sessions as preview

    original = preview.async_fs.iterdir
    created = []

    async def list_after_creation(path):
        created.append(await manager.create_session("srv1"))
        return await original(path)

    monkeypatch.setattr(preview.async_fs, "iterdir", list_after_creation)
    assert await manager.reap_orphan_dirs() == []
    assert created[0].is_dir()
    assert manager.get_active_for_server("srv1") == created[0].name


async def test_cancel_during_session_directory_creation_waits_and_cleans(manager, monkeypatch):
    from app.snapshots import preview_sessions as preview

    original = preview.aioos.makedirs
    created = asyncio.Event()
    finish = asyncio.Event()

    async def blocked_mkdir(*args, **kwargs):
        await original(*args, **kwargs)
        created.set()
        await finish.wait()

    monkeypatch.setattr(preview.aioos, "makedirs", blocked_mkdir)
    task = asyncio.create_task(manager.create_session("srv1"))
    await asyncio.wait_for(created.wait(), 5)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert manager.get_active_for_server("srv1") is None
    assert not manager._sessions
    assert not list(manager.base_dir.iterdir())


def _restore_config(
    *,
    ttl_seconds: int = 60,
    janitor_interval_seconds: int = 5,
    region_bytes: int = default_region_bytes,
):
    return SimpleNamespace(
        preview_session_ttl_seconds=ttl_seconds,
        preview_janitor_interval_seconds=janitor_interval_seconds,
        preview_avg_region_bytes=region_bytes,
    )


def _runtime_config(**kwargs):
    values = vars(get_config()) | {
        "snapshots": SimpleNamespace(**(vars(get_config().snapshots) | {"world_restore": _restore_config(**kwargs)}))
    }
    return SimpleNamespace(**values)


@pytest.fixture
def base_dir():
    with tempfile.TemporaryDirectory(prefix="preview-test-") as tmp:
        yield Path(tmp)


@pytest.fixture
def manager(base_dir, monkeypatch):
    set_runtime_resource(monkeypatch, 'dynamic_configuration', _runtime_config())
    return PreviewSessionManager(base_dir=base_dir)


@pytest.mark.asyncio
async def test_create_session_makes_directory(manager, base_dir):
    session_dir = await manager.create_session("srv1", affected_regions=4)
    assert session_dir.is_dir()
    assert session_dir.parent == base_dir
    sid = session_dir.name
    assert manager.get_active_for_server("srv1") == sid


@pytest.mark.asyncio
async def test_end_session_is_idempotent_and_removes_dir(manager):
    session_dir = await manager.create_session("srv1")
    sid = session_dir.name
    (session_dir / "stub.txt").write_text("hello")
    await manager.end(sid)
    assert not session_dir.exists()
    # Calling end again does not raise.
    await manager.end(sid)
    assert manager.get_active_for_server("srv1") is None


@pytest.mark.asyncio
async def test_heartbeat_updates_last_seen(manager):
    session_dir = await manager.create_session("srv1")
    sid = session_dir.name
    initial = manager._sessions[sid].last_seen
    # Force an artificially old last_seen, then heartbeat.
    manager._sessions[sid].last_seen = initial - timedelta(seconds=30)
    manager.heartbeat(sid)
    assert manager._sessions[sid].last_seen > initial - timedelta(seconds=30)


def test_heartbeat_unknown_session_raises(manager):
    with pytest.raises(PreviewSessionNotFoundError):
        manager.heartbeat("doesnotexist")


async def test_heartbeat_cannot_revive_expired_preview(manager):
    directory = await manager.create_session("srv1")
    session = manager._sessions[directory.name]
    session.last_seen = manager._now() - timedelta(seconds=61)
    with pytest.raises(PreviewSessionNotFoundError):
        manager.heartbeat(directory.name)
    await manager.reap_stale()
    assert not directory.exists()


@pytest.mark.parametrize("trigger", ["close", "expiry", "replacement"])
async def test_active_preview_reference_delays_cleanup(manager, trigger):
    directory = await manager.create_session("srv1")
    (directory / "source.mca").write_bytes(b"owned source")
    queue = SimpleNamespace(close=AsyncMock())
    manager.attach_render_queue(directory.name, queue=queue, affected_keys={(0, 0)})
    async with manager.use(directory.name):
        if trigger == "expiry":
            manager._sessions[directory.name].last_seen = manager._now() - timedelta(seconds=61)
            await manager.reap_stale()
        elif trigger == "replacement":
            await manager.create_session("srv1")
        else:
            await manager.end(directory.name)
        await manager.reap_orphan_dirs()
        assert (directory / "source.mca").read_bytes() == b"owned source"
        queue.close.assert_not_awaited()
        with pytest.raises(PreviewSessionNotFoundError):
            manager.heartbeat(directory.name)
    queue.close.assert_awaited_once()
    assert not directory.exists()


@pytest.mark.asyncio
async def test_one_preview_per_server_replaces_prior(manager):
    first = await manager.create_session("srv1")
    first_sid = first.name
    # Touch a file in the first session so we can verify it's gone.
    (first / "marker.txt").write_text("x")
    second = await manager.create_session("srv1")
    assert second != first
    assert not first.exists(), "prior session dir must be removed"
    assert manager.get_active_for_server("srv1") == second.name
    assert first_sid not in manager._sessions


@pytest.mark.asyncio
async def test_reap_stale_sessions(manager):
    """Sessions older than TTL are reaped; fresh sessions survive."""
    fresh = await manager.create_session("srv1")
    stale = await manager.create_session("srv2")
    stale_sid = stale.name
    # Force stale session's last_seen to be older than TTL.
    manager._sessions[stale_sid].last_seen = datetime.now(UTC) - timedelta(
        seconds=60 + 60
    )
    reaped = await manager.reap_stale()
    assert reaped == [stale_sid]
    assert not stale.exists()
    assert fresh.exists()
    assert manager.get_active_for_server("srv2") is None
    assert manager.get_active_for_server("srv1") == fresh.name


@pytest.mark.asyncio
async def test_reap_orphan_dirs(manager, base_dir):
    """Subdirs of base_dir with no in-memory entry are deleted."""
    orphan = base_dir / "orphan-from-prior-process"
    orphan.mkdir()
    (orphan / "trash.txt").write_text("ignored")

    # Live session should NOT be reaped.
    live = await manager.create_session("srv1")
    deleted = await manager.reap_orphan_dirs()
    assert orphan in deleted
    assert not orphan.exists()
    assert live.exists()


@pytest.mark.asyncio
async def test_disk_guard_raises_when_free_too_low(manager):
    """Mock disk_free_bytes to simulate near-full disk."""
    with patch.object(
        manager, "disk_free_bytes", new=AsyncMock(return_value=default_region_bytes)
    ), pytest.raises(PreviewDiskGuardError) as exc:
        await manager.create_session("srv1", affected_regions=100)
    assert exc.value.free == default_region_bytes
    assert exc.value.required > exc.value.free


@pytest.mark.asyncio
async def test_disk_guard_uses_dynamic_region_size(manager, monkeypatch):
    set_runtime_resource(monkeypatch, 'dynamic_configuration', _runtime_config(region_bytes=4096))
    with (
        patch.object(manager, 'disk_free_bytes', new=AsyncMock(return_value=4096)),
        pytest.raises(PreviewDiskGuardError) as exc,
    ):
        await manager.create_session("srv1", affected_regions=1)
    assert exc.value.required == 4096 * 2


@pytest.mark.asyncio
async def test_get_tile_path_returns_none_when_missing(manager):
    session_dir = await manager.create_session("srv1")
    sid = session_dir.name
    assert await manager.get_tile_path(sid, 0, 0) is None
    tile = session_dir / "tiles" / "r.0.0.png"
    tile.parent.mkdir()
    tile.write_bytes(b"PNG-stub")
    assert await manager.get_tile_path(sid, 0, 0) == tile


@pytest.mark.asyncio
async def test_get_tile_path_unknown_session_returns_none(manager):
    assert await manager.get_tile_path("nonexistent", 0, 0) is None


@pytest.mark.asyncio
async def test_janitor_loop_starts_and_stops_cleanly(manager):
    task = manager.start_janitor()
    assert not task.done()
    # Idempotent — calling again returns the same task.
    assert manager.start_janitor() is task
    await manager.stop_janitor()
    assert task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_janitor_reaps_stale_in_background(base_dir, monkeypatch):
    """End-to-end: spin up a janitor with a tight interval; create a stale
    session; verify it's reaped within a reasonable time window."""
    set_runtime_resource(monkeypatch, 'dynamic_configuration', _runtime_config(ttl_seconds=1, janitor_interval_seconds=1))
    manager = PreviewSessionManager(base_dir=base_dir)
    session_dir = await manager.create_session("srv1")
    sid = session_dir.name
    # Backdate last_seen so it's already stale.
    manager._sessions[sid].last_seen = datetime.now(UTC) - timedelta(seconds=10)
    manager.start_janitor()
    try:
        # Wait up to 5s for the janitor to reap.
        for _ in range(50):
            if sid not in manager._sessions:
                break
            await asyncio.sleep(0.1)
        assert sid not in manager._sessions
        assert not session_dir.exists()
    finally:
        await manager.stop_janitor()


async def test_global_preview_replacement_releases_all_overlapping_server_owners(manager):
    first = await manager.create_session("srv1", source_snapshot_id="first")
    second = await manager.create_session("srv2", source_snapshot_id="second")
    global_preview = await manager.create_session(
        None, server_ids=("srv1", "srv2"), source_snapshot_id="global-source"
    )
    assert not first.exists() and not second.exists()
    assert manager.get_active_for_server("srv1") == global_preview.name
    assert manager.get_active_for_server("srv2") == global_preview.name
    replacement = await manager.create_session("srv2", source_snapshot_id="replacement")
    assert not global_preview.exists()
    assert manager.get_active_for_server("srv1") is None
    assert manager.get_active_for_server(None) is None
    assert manager._repository_use.active_snapshots == {"replacement"}
    await manager.end_and_wait(replacement.name)
    assert not manager._repository_use.active_snapshots


async def test_cleanup_and_restart_preserve_unknown_preview_writer_artifacts(
    manager, isolated_runtime,
):
    from app.db.metadata import Base
    from app.operations.journal import OperationJournal
    from app.operations.journal_types import (
        OperationSpec,
        OperationState,
        RecoveryReference,
        ResourceReference,
    )

    async with isolated_runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    journal = OperationJournal(isolated_runtime.database.session_factory)
    isolated_runtime.journal = journal
    directory = await manager.create_session("srv1", source_snapshot_id="source")
    record = await journal.accept(OperationSpec(
        kind="world_preview_render", resources=(ResourceReference("cache", "srv1", 1),)
    ))
    await journal.start(record.operation_id)
    await journal.phase(record.operation_id, "rendering", recovery_refs=(RecoveryReference("world_preview", directory.name),))
    await journal.set_ownership_known(record.operation_id, False)
    await journal.finish(record.operation_id, OperationState.INTERRUPTED, writers_stopped=False)
    with pytest.raises(HTTPException, match="预览写入状态尚未确认"):
        await manager.end_and_wait(directory.name)
    assert directory.exists()
    assert manager._repository_use.active_snapshots == {"source"}
    restarted = PreviewSessionManager(manager.base_dir)
    assert await restarted.reap_orphan_dirs() == []
    with pytest.raises(PreviewSessionNotFoundError):
        restarted.heartbeat(directory.name)
    await journal.resolve(record.operation_id, actor_id=0, writers_stopped=True, resolve_references=True)
    assert await restarted.reap_orphan_dirs() == [directory]
    await manager.end_and_wait(directory.name)
    assert not manager._repository_use.active_snapshots
