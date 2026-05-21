"""Tests for PreviewSessionManager: create/heartbeat/end, janitor reaping,
disk guard, one-preview-per-server enforcement."""

import asyncio
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.dynamic_config.configs.snapshots import WorldRestoreConfig
from app.world.preview import (
    PreviewDiskGuardError,
    PreviewSessionManager,
    PreviewSessionNotFoundError,
)

default_region_bytes = WorldRestoreConfig().preview_avg_region_bytes


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
    return SimpleNamespace(
        snapshots=SimpleNamespace(world_restore=_restore_config(**kwargs))
    )


@pytest.fixture
def base_dir():
    with tempfile.TemporaryDirectory(prefix="preview-test-") as tmp:
        yield Path(tmp)


@pytest.fixture
def manager(base_dir, monkeypatch):
    monkeypatch.setattr(
        "app.world.preview.config",
        _runtime_config(),
    )
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
    manager._sessions[sid].last_seen = initial - timedelta(minutes=5)
    manager.heartbeat(sid)
    assert manager._sessions[sid].last_seen > initial - timedelta(minutes=5)


def test_heartbeat_unknown_session_raises(manager):
    with pytest.raises(PreviewSessionNotFoundError):
        manager.heartbeat("doesnotexist")


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
    manager._sessions[stale_sid].last_seen = datetime.now(timezone.utc) - timedelta(
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
    ):
        with pytest.raises(PreviewDiskGuardError) as exc:
            await manager.create_session("srv1", affected_regions=100)
    assert exc.value.free == default_region_bytes
    assert exc.value.required > exc.value.free


@pytest.mark.asyncio
async def test_disk_guard_uses_dynamic_region_size(manager, monkeypatch):
    monkeypatch.setattr(
        "app.world.preview.config",
        _runtime_config(region_bytes=4096),
    )
    with patch.object(manager, "disk_free_bytes", new=AsyncMock(return_value=4096)):
        with pytest.raises(PreviewDiskGuardError) as exc:
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
    monkeypatch.setattr(
        "app.world.preview.config",
        _runtime_config(ttl_seconds=1, janitor_interval_seconds=1),
    )
    manager = PreviewSessionManager(base_dir=base_dir)
    session_dir = await manager.create_session("srv1")
    sid = session_dir.name
    # Backdate last_seen so it's already stale.
    manager._sessions[sid].last_seen = datetime.now(timezone.utc) - timedelta(seconds=10)
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
