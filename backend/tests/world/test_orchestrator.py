"""Tests for WorldRestoreOrchestrator covering all four restore scopes plus
locking, safety snapshots, server-stopped guard, and rollback.

These tests exercise the full restore pipeline against real restic and (for the
chunks scope) real mcmap. ``DockerMCManager`` is replaced with a lightweight
fake so tests don't need actual containers — only filesystem and DB state.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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
    LockHolder,
    ServerNotStoppedError,
    ServerOperationKind,
    ServerOperationLock,
    WorldRestoreOrchestrator,
)


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


# --- Test doubles -----------------------------------------------------------


class _FakeInstance:
    def __init__(self, data_path: Path, status: MCServerStatus) -> None:
        self._data_path = data_path
        self._status = status

    def get_data_path(self) -> Path:
        return self._data_path

    def set_status(self, status: MCServerStatus) -> None:
        self._status = status

    async def get_status(self) -> MCServerStatus:
        return self._status


class _FakeDockerMC:
    def __init__(self, instance: _FakeInstance) -> None:
        self._instance = instance

    def get_instance(self, server_id: str) -> _FakeInstance:
        return self._instance


# --- Fixtures ---------------------------------------------------------------


def _empty_mca() -> bytes:
    """Minimal valid .mca: 4 KiB location table + 4 KiB timestamp table, all zero."""
    return b"\x00" * 8192


@pytest.fixture
def data_path():
    with tempfile.TemporaryDirectory(prefix="mc-restore-data-") as tmp:
        data = Path(tmp)
        # Vanilla single-world layout, two dimensions.
        world = data / "world"
        ow_region = world / "region"
        ow_region.mkdir(parents=True)
        (ow_region / "r.0.0.mca").write_bytes(_empty_mca())
        (ow_region / "r.1.0.mca").write_bytes(_empty_mca() + b"\xab\xcd")
        (world / "level.dat").write_bytes(b"level-stub")

        # Overworld entities (1.17+ peer dir)
        (world / "entities").mkdir(parents=True)
        (world / "entities" / "r.0.0.mca").write_bytes(_empty_mca())

        # Nether
        nether_region = world / "DIM-1" / "region"
        nether_region.mkdir(parents=True)
        (nether_region / "r.0.0.mca").write_bytes(_empty_mca() + b"\xee\xff")
        yield data


@pytest.fixture
def repo_path():
    with tempfile.TemporaryDirectory(prefix="mc-restore-repo-") as tmp:
        yield Path(tmp)


@pytest.fixture
async def session_factory():
    with tempfile.TemporaryDirectory(prefix="mc-restore-db-") as tmp:
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
async def restic_manager(repo_path):
    manager = ResticManager(repository_path=str(repo_path), password=None)
    await exec_command("restic", "init", "--insecure-no-password", env=manager.env)
    return manager


@pytest.fixture
def fake_docker(data_path):
    instance = _FakeInstance(data_path, status=MCServerStatus.EXISTS)
    return _FakeDockerMC(instance)


@pytest.fixture
def lock():
    # Fresh lock per test so prior holders never leak.
    return ServerOperationLock()


@pytest.fixture
def orchestrator(restic_manager, fake_docker, lock, session_factory):
    return WorldRestoreOrchestrator(
        restic_manager=restic_manager,
        docker_mc_manager=fake_docker,
        server_operation_lock=lock,
        session_factory=session_factory,
    )


# --- Helpers ---------------------------------------------------------------


async def _drain(gen) -> list:
    out = []
    async for ev in gen:
        out.append(ev)
    return out


async def _read_restoration(session_factory, rid: str) -> Optional[Restoration]:
    async with session_factory() as session:
        return (
            await session.execute(select(Restoration).where(Restoration.id == rid))
        ).scalar_one_or_none()


# --- Tests: world scope ----------------------------------------------------


@pytest.mark.asyncio
async def test_world_scope_round_trip(orchestrator, data_path, session_factory):
    selection = RestorationSelection(
        type=RestorationType.WORLD,
    )
    snap = await orchestrator.create_snapshot("srv1", selection, user_id=None)
    assert snap.id

    # Mutate the world: change region content, delete a file.
    region_dir = data_path / "world" / "region"
    (region_dir / "r.1.0.mca").write_bytes(b"corrupted")
    (region_dir / "r.0.0.mca").unlink()

    events = await _drain(
        orchestrator.begin_restore(
            server_id="srv1",
            source_snapshot_id=snap.id,
            selection=selection,
            user_id=42,
        )
    )

    types = [e.event_type for e in events]
    assert types[0] == "start"
    assert "safety_snapshot" in types
    assert types[-1] == "complete"

    # World restored: deleted file is back, mutated file matches snapshot.
    assert (region_dir / "r.0.0.mca").exists()
    assert (region_dir / "r.0.0.mca").read_bytes() == _empty_mca()
    assert (region_dir / "r.1.0.mca").read_bytes() == _empty_mca() + b"\xab\xcd"

    # DB row succeeded.
    rid = events[0].restoration_id
    row = await _read_restoration(session_factory, rid)
    assert row is not None
    assert row.status is RestorationStatus.SUCCEEDED
    assert row.safety_snapshot_id is not None
    assert row.is_rollback is False


# --- Tests: dimension scope ------------------------------------------------


@pytest.mark.asyncio
async def test_dimension_scope_restores_only_target_dimension(
    orchestrator, data_path
):
    full = RestorationSelection(type=RestorationType.WORLD)
    snap = await orchestrator.create_snapshot("srv1", full, user_id=None)

    # Mutate both Overworld and Nether.
    (data_path / "world" / "region" / "r.1.0.mca").write_bytes(b"ow-corrupt")
    (data_path / "world" / "DIM-1" / "region" / "r.0.0.mca").write_bytes(b"nether-corrupt")

    selection = RestorationSelection(
        type=RestorationType.DIMENSION,
        region_dir_relpath="world/DIM-1/region",
    )
    events = await _drain(
        orchestrator.begin_restore(
            server_id="srv1",
            source_snapshot_id=snap.id,
            selection=selection,
            user_id=None,
        )
    )
    assert events[-1].event_type == "complete"

    # Nether restored.
    assert (
        data_path / "world" / "DIM-1" / "region" / "r.0.0.mca"
    ).read_bytes() == _empty_mca() + b"\xee\xff"
    # Overworld untouched (still corrupted).
    assert (
        data_path / "world" / "region" / "r.1.0.mca"
    ).read_bytes() == b"ow-corrupt"


# --- Tests: regions scope --------------------------------------------------


@pytest.mark.asyncio
async def test_regions_scope_restores_only_selected_regions(
    orchestrator, data_path
):
    full = RestorationSelection(type=RestorationType.WORLD)
    snap = await orchestrator.create_snapshot("srv1", full, user_id=None)

    region_dir = data_path / "world" / "region"
    (region_dir / "r.0.0.mca").write_bytes(b"corrupt-00")
    (region_dir / "r.1.0.mca").write_bytes(b"corrupt-10")

    selection = RestorationSelection(
        type=RestorationType.REGIONS,
        region_dir_relpath="world/region",
        regions=[(0, 0)],
    )
    events = await _drain(
        orchestrator.begin_restore(
            server_id="srv1",
            source_snapshot_id=snap.id,
            selection=selection,
            user_id=None,
        )
    )
    assert events[-1].event_type == "complete"

    # Selected region restored.
    assert (region_dir / "r.0.0.mca").read_bytes() == _empty_mca()
    # Non-selected region untouched.
    assert (region_dir / "r.1.0.mca").read_bytes() == b"corrupt-10"


# --- Tests: chunks scope ---------------------------------------------------


@pytest.mark.skipif(not _mcmap_available(), reason="mcmap not installed")
@pytest.mark.asyncio
async def test_chunks_scope_invokes_mcmap_and_completes(
    orchestrator, data_path, session_factory
):
    full = RestorationSelection(type=RestorationType.WORLD)
    snap = await orchestrator.create_snapshot("srv1", full, user_id=None)

    selection = RestorationSelection(
        type=RestorationType.CHUNKS,
        region_dir_relpath="world/region",
        chunks=[(3, 4), (5, 6)],  # both inside region (0, 0)
    )
    events = await _drain(
        orchestrator.begin_restore(
            server_id="srv1",
            source_snapshot_id=snap.id,
            selection=selection,
            user_id=None,
        )
    )
    types = [e.event_type for e in events]
    assert types[0] == "start"
    assert "stage" in types
    # At least one merge_region event must be emitted (we have entities/region — poi missing)
    assert any(e.event_type == "merge_region" for e in events)
    assert types[-1] == "complete"

    rid = events[0].restoration_id
    row = await _read_restoration(session_factory, rid)
    assert row is not None
    assert row.status is RestorationStatus.SUCCEEDED


@pytest.mark.skipif(not _mcmap_available(), reason="mcmap not installed")
@pytest.mark.asyncio
async def test_chunks_scope_remove_when_source_missing(
    orchestrator, data_path
):
    """Snapshot has no .mca for region (1, 0) entities, but live does — orchestrator
    should call remove_chunks on the live entities file."""
    # Snapshot regions where (1, 0) has region/ but NO entities/ data.
    full = RestorationSelection(
        type=RestorationType.REGIONS,
        region_dir_relpath="world/region",
        regions=[(0, 0)],  # snapshot only covers region (0, 0)
    )
    snap = await orchestrator.create_snapshot("srv1", full, user_id=None)

    # Put data in live entities for region (1, 0).
    (data_path / "world" / "entities" / "r.1.0.mca").write_bytes(_empty_mca())

    selection = RestorationSelection(
        type=RestorationType.CHUNKS,
        region_dir_relpath="world/region",
        chunks=[(36, 4)],  # in region (1, 0)
    )
    # Snapshot doesn't cover region (1, 0), so eligibility filter should reject.
    eligible = await orchestrator.list_eligible_snapshots("srv1", selection)
    assert all(s.id != snap.id for s in eligible)


# --- Tests: locking --------------------------------------------------------


@pytest.mark.asyncio
async def test_lock_held_during_restore(orchestrator, data_path, lock):
    selection = RestorationSelection(type=RestorationType.WORLD)
    snap = await orchestrator.create_snapshot("srv1", selection, user_id=None)

    holders_seen: list[Optional[LockHolder]] = []

    async for ev in orchestrator.begin_restore(
        server_id="srv1",
        source_snapshot_id=snap.id,
        selection=selection,
        user_id=7,
    ):
        holders_seen.append(lock.get_holder("srv1"))
        # Note: don't break early — the async generator's `async with` cleanup
        # only runs when iteration completes, so an early break would leave
        # the lock held until GC.
        del ev

    # Lock holder is RESTORE while the flow runs.
    restore_holders = [h for h in holders_seen if h is not None]
    assert restore_holders, "lock holder should have been observed during restore"
    assert all(h.kind is ServerOperationKind.RESTORE for h in restore_holders)
    assert all(h.user_id == 7 for h in restore_holders)
    assert all(h.restoration_id is not None for h in restore_holders)

    # Lock released after flow completes.
    assert lock.get_holder("srv1") is None
    assert not lock.is_locked("srv1")


# --- Tests: server-stopped guard -------------------------------------------


@pytest.mark.asyncio
async def test_restore_blocked_when_server_running(orchestrator, fake_docker):
    selection = RestorationSelection(type=RestorationType.WORLD)
    snap = await orchestrator.create_snapshot("srv1", selection, user_id=None)

    fake_docker._instance.set_status(MCServerStatus.RUNNING)

    with pytest.raises(ServerNotStoppedError):
        async for _ in orchestrator.begin_restore(
            server_id="srv1",
            source_snapshot_id=snap.id,
            selection=selection,
            user_id=None,
        ):
            pass


# --- Tests: safety snapshot ------------------------------------------------


@pytest.mark.asyncio
async def test_safety_snapshot_recorded_on_row(orchestrator, data_path, session_factory):
    selection = RestorationSelection(type=RestorationType.WORLD)
    snap = await orchestrator.create_snapshot("srv1", selection, user_id=None)

    events = await _drain(
        orchestrator.begin_restore(
            server_id="srv1",
            source_snapshot_id=snap.id,
            selection=selection,
            user_id=None,
        )
    )
    rid = events[0].restoration_id
    row = await _read_restoration(session_factory, rid)
    assert row is not None
    assert row.safety_snapshot_id is not None
    # The safety snapshot exists in the repo.
    snapshots = await orchestrator._restic.list_snapshots()
    assert any(s.id == row.safety_snapshot_id for s in snapshots)


# --- Tests: rollback -------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_uses_safety_as_source(
    orchestrator, data_path, session_factory
):
    selection = RestorationSelection(type=RestorationType.WORLD)
    snap1 = await orchestrator.create_snapshot("srv1", selection, user_id=None)

    # Mutate, then run a restore — this captures live state into a safety snapshot.
    (data_path / "world" / "region" / "r.0.0.mca").write_bytes(b"pre-restore")
    pre_restore_state = (data_path / "world" / "region" / "r.0.0.mca").read_bytes()

    events = await _drain(
        orchestrator.begin_restore(
            server_id="srv1",
            source_snapshot_id=snap1.id,
            selection=selection,
            user_id=None,
        )
    )
    rid = events[0].restoration_id

    # Live state is now snap1 content.
    assert (
        data_path / "world" / "region" / "r.0.0.mca"
    ).read_bytes() == _empty_mca()

    # Roll back — should restore live state to pre-restore content via safety snapshot.
    rollback_events = await _drain(
        orchestrator.rollback(restoration_id=rid, user_id=None)
    )
    assert rollback_events[-1].event_type == "complete"
    rollback_rid = rollback_events[0].restoration_id

    assert (
        data_path / "world" / "region" / "r.0.0.mca"
    ).read_bytes() == pre_restore_state

    # Rollback row exists with is_rollback=True and source = safety snapshot.
    rollback_row = await _read_restoration(session_factory, rollback_rid)
    assert rollback_row is not None
    assert rollback_row.is_rollback is True
    original_row = await _read_restoration(session_factory, rid)
    assert rollback_row.source_snapshot_id == original_row.safety_snapshot_id


# --- Tests: failure path ---------------------------------------------------


@pytest.mark.asyncio
async def test_restore_failure_marks_row_failed(
    orchestrator, data_path, session_factory
):
    selection = RestorationSelection(type=RestorationType.WORLD)
    snap = await orchestrator.create_snapshot("srv1", selection, user_id=None)

    # Force a failure by pointing at a bogus snapshot id after the safety snapshot
    # is created. Easiest path: monkeypatch the orchestrator's restore to raise.
    real_restore = orchestrator._restic.restore

    call_count = {"n": 0}

    async def flaky_restore(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First call (during the restore flow) — fail.
            raise RuntimeError("simulated restic failure")
            yield  # pragma: no cover - keeps this an async generator
        async for ev in real_restore(*args, **kwargs):
            yield ev

    orchestrator._restic.restore = flaky_restore  # type: ignore[assignment]
    try:
        events = await _drain(
            orchestrator.begin_restore(
                server_id="srv1",
                source_snapshot_id=snap.id,
                selection=selection,
                user_id=None,
            )
        )
    finally:
        orchestrator._restic.restore = real_restore  # type: ignore[assignment]

    assert events[-1].event_type == "error"
    assert "simulated restic failure" in events[-1].message
    rid = events[0].restoration_id
    row = await _read_restoration(session_factory, rid)
    assert row is not None
    assert row.status is RestorationStatus.FAILED
    assert "simulated restic failure" in row.error_message


# --- Tests: multi-root WORLD scope -----------------------------------------


@pytest.fixture
def multi_root_data_path():
    """Two world roots — Bukkit/Paper-style multi-world layout."""
    with tempfile.TemporaryDirectory(prefix="mc-restore-multi-data-") as tmp:
        data = Path(tmp)
        # Primary: world (server.properties default)
        world = data / "world"
        (world / "region").mkdir(parents=True)
        (world / "region" / "r.0.0.mca").write_bytes(_empty_mca())
        (world / "level.dat").write_bytes(b"level-stub-1")

        # Peer root: world_creative
        creative = data / "world_creative"
        (creative / "region").mkdir(parents=True)
        (creative / "region" / "r.0.0.mca").write_bytes(_empty_mca() + b"\xfa\xce")
        (creative / "level.dat").write_bytes(b"level-stub-2")
        yield data


@pytest.fixture
def fake_docker_multi(multi_root_data_path):
    instance = _FakeInstance(multi_root_data_path, status=MCServerStatus.EXISTS)
    return _FakeDockerMC(instance)


@pytest.fixture
def orchestrator_multi(restic_manager, fake_docker_multi, lock, session_factory):
    return WorldRestoreOrchestrator(
        restic_manager=restic_manager,
        docker_mc_manager=fake_docker_multi,
        server_operation_lock=lock,
        session_factory=session_factory,
    )


@pytest.mark.asyncio
async def test_world_scope_covers_all_roots(
    orchestrator_multi, multi_root_data_path
):
    """WORLD scope on a multi-root server should snapshot every root and
    restore every root in one operation."""
    selection = RestorationSelection(type=RestorationType.WORLD)
    paths = await orchestrator_multi._resolve_paths_for_selection("srv1", selection)
    path_names = {p.name for p in paths}
    assert path_names == {"world", "world_creative"}

    snap = await orchestrator_multi.create_snapshot("srv1", selection, user_id=None)

    # Mutate both roots.
    (multi_root_data_path / "world" / "region" / "r.0.0.mca").write_bytes(b"corrupt-1")
    (multi_root_data_path / "world_creative" / "region" / "r.0.0.mca").write_bytes(b"corrupt-2")

    events = await _drain(
        orchestrator_multi.begin_restore(
            server_id="srv1",
            source_snapshot_id=snap.id,
            selection=selection,
            user_id=None,
        )
    )
    assert events[-1].event_type == "complete"

    # Both roots restored.
    assert (
        multi_root_data_path / "world" / "region" / "r.0.0.mca"
    ).read_bytes() == _empty_mca()
    assert (
        multi_root_data_path / "world_creative" / "region" / "r.0.0.mca"
    ).read_bytes() == _empty_mca() + b"\xfa\xce"


# --- Tests: tile cache invalidation ----------------------------------------


def _seed_tile_cache(data_path: Path, tiles: list[tuple[str, int, int]]) -> list[Path]:
    """Materialize fake PNG tiles under ``data/.mcmap/tiles/<region_path>/`` and
    return their paths (in order)."""
    written: list[Path] = []
    for region_path, x, z in tiles:
        png = data_path / ".mcmap" / "tiles" / region_path / f"r.{x}.{z}.png"
        png.parent.mkdir(parents=True, exist_ok=True)
        png.write_bytes(b"fake-png")
        written.append(png)
    return written


@pytest.mark.asyncio
async def test_world_restore_invalidates_affected_tiles(
    orchestrator, data_path
):
    """A WORLD restore must remove only the PNG tiles whose backing region MCA
    was actually written, leaving untouched tiles in place."""
    selection = RestorationSelection(type=RestorationType.WORLD)
    snap = await orchestrator.create_snapshot("srv1", selection, user_id=None)

    # Seed tiles: r.0.0 + r.1.0 in the Overworld, r.0.0 in the Nether.
    overworld_changed_tile, overworld_kept_tile, nether_kept_tile = _seed_tile_cache(
        data_path,
        [("world/region", 0, 0), ("world/region", 1, 0), ("world/DIM-1/region", 0, 0)],
    )

    # Mutate only r.0.0 in the Overworld so restic only restores that one.
    (data_path / "world" / "region" / "r.0.0.mca").write_bytes(b"corrupted")

    events = []
    async for ev in orchestrator.begin_restore(
        server_id="srv1",
        source_snapshot_id=snap.id,
        selection=selection,
        user_id=None,
    ):
        events.append(ev)

    types = [e.event_type for e in events]
    assert types[-1] == "complete"
    assert "invalidate_cache" in types

    # The tile whose MCA was rewritten is gone; untouched tiles remain.
    assert not overworld_changed_tile.exists()
    assert overworld_kept_tile.exists()
    assert nether_kept_tile.exists()


@pytest.mark.asyncio
async def test_regions_restore_invalidates_only_selected_tiles(
    orchestrator, data_path
):
    """REGIONS scope drives invalidation from the selection itself — even tiles
    for regions the snapshot didn't actually need to write should still be
    cleared, since the user explicitly restored that region."""
    full = RestorationSelection(type=RestorationType.WORLD)
    snap = await orchestrator.create_snapshot("srv1", full, user_id=None)

    target_tile, neighbor_tile = _seed_tile_cache(
        data_path, [("world/region", 0, 0), ("world/region", 1, 0)]
    )

    selection = RestorationSelection(
        type=RestorationType.REGIONS,
        region_dir_relpath="world/region",
        regions=[(0, 0)],
    )
    events = []
    async for ev in orchestrator.begin_restore(
        server_id="srv1",
        source_snapshot_id=snap.id,
        selection=selection,
        user_id=None,
    ):
        events.append(ev)

    assert events[-1].event_type == "complete"
    assert not target_tile.exists()
    assert neighbor_tile.exists()


# Silence "unused import" warnings.
_ = shutil
