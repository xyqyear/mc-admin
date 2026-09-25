import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.servers.references import ServerRef
from app.world.events import RestoreEvent, SelectionResolutionError
from app.world.models import Restoration, RestorationType
from app.world.restore import WorldRestoreOrchestrator
from app.world.schemas import RestorationSelection
from app.world.scope_execution import RestoreScopeExecutor, safety_backup_paths
from app.world.selection import absent_directories, resolve_paths


@pytest.mark.parametrize("scope", list(RestorationType))
@pytest.mark.parametrize("failure", ["error", "cancel"])
async def test_empty_backup_evidence_is_scoped_and_cleaned_on_failure(tmp_path, scope, failure):
    data = tmp_path / "data"
    data.mkdir()
    untouched = data / "config.yml"
    untouched.write_bytes(b"outside selected world")
    selection = RestorationSelection(
        type=scope, region_dir_relpath="world/region" if scope is not RestorationType.WORLD else None,
        regions=[(0, 0)] if scope is RestorationType.REGIONS else [],
        chunks=[(0, 0)] if scope is RestorationType.CHUNKS else [],
    )
    paths = await resolve_paths(data, selection, include_mcc=True, include_missing=True,
                                allow_missing_dimension=True, world_roots=["world"] if scope is RestorationType.WORLD else None)
    missing = await absent_directories(data, paths, selection)
    prepared = asyncio.Event()

    async def backup():
        async with safety_backup_paths(data, paths, selection, missing) as selected:
            assert selected
            assert all(path.is_dir() and path.is_relative_to(data / "world") for path in selected)
            if scope in (RestorationType.REGIONS, RestorationType.CHUNKS):
                assert all(path.name.startswith(".mc-admin-absence-") for path in selected)
            prepared.set()
            if failure == "error":
                raise RuntimeError("controlled backup failure")
            await asyncio.Event().wait()

    task = asyncio.create_task(backup())
    await asyncio.wait_for(prepared.wait(), 5)
    if failure == "cancel":
        task.cancel()
    with pytest.raises(asyncio.CancelledError if failure == "cancel" else RuntimeError):
        await task
    assert not (data / "world").exists()
    assert untouched.read_bytes() == b"outside selected world"


@pytest.mark.parametrize("relative", ["../outside", "/tmp/outside", ".", "world/../other/region"])
async def test_history_missing_dimension_rejects_unconfined_paths(tmp_path, relative):
    selection = RestorationSelection(type=RestorationType.DIMENSION, region_dir_relpath=relative)
    with pytest.raises(SelectionResolutionError):
        await resolve_paths(tmp_path, selection, include_mcc=True, allow_missing_dimension=True)


async def test_history_missing_dimension_rejects_external_symlink(tmp_path):
    data = tmp_path / "data"
    outside = tmp_path / "outside"
    data.mkdir()
    outside.mkdir()
    (data / "world").symlink_to(outside, target_is_directory=True)
    selection = RestorationSelection(type=RestorationType.REGIONS, region_dir_relpath="world/region", regions=[(0, 0)])
    with pytest.raises(SelectionResolutionError):
        await resolve_paths(data, selection, include_mcc=True, allow_missing_dimension=True)


async def test_recorded_absence_cannot_remove_sibling_scope(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    sibling = data / "other"
    sibling.mkdir()
    (sibling / "keep").write_bytes(b"not selected")
    snapshots = AsyncMock()
    selection = RestorationSelection(type=RestorationType.WORLD)
    with pytest.raises(SelectionResolutionError):
        await RestoreScopeExecutor(snapshots)._restore_absent_sidecars(data, "snapshot", selection, ["other"], [data / "world"])
    snapshots.remove_absent_paths.assert_not_awaited()
    assert (sibling / "keep").read_bytes() == b"not selected"


@pytest.mark.parametrize("snapshot_path", ["world", "data-root", "outside"])
async def test_legacy_world_rollback_derives_only_confined_snapshot_scope(tmp_path, monkeypatch, snapshot_path):
    data = tmp_path / "srv1" / "data"
    data.mkdir(parents=True)
    reference = ServerRef("srv1", 7, tmp_path, data.parent, data)
    row = Restoration(id="restoration", server_id="srv1", server_generation=7,
                      type=RestorationType.WORLD, source_snapshot_id="source", safety_snapshot_id="safety",
                      selection_json=json.dumps({"type": "world", "absent_sidecar_dirs": []}))
    path = data / "world" if snapshot_path == "world" else data if snapshot_path == "data-root" else tmp_path / "outside"
    orchestrator = WorldRestoreOrchestrator.__new__(WorldRestoreOrchestrator)
    orchestrator._store = AsyncMock()
    orchestrator._store.get.return_value = row
    orchestrator._snapshots = AsyncMock()
    orchestrator._snapshots.get_snapshot.return_value = SimpleNamespace(paths=[str(path)])
    monkeypatch.setattr(orchestrator, "_reference", AsyncMock(return_value=reference))
    captured = []

    async def restore(**kwargs):
        captured.append(kwargs)
        yield RestoreEvent(event_type="complete", restoration_id="new-restoration")

    monkeypatch.setattr(orchestrator, "begin_restore", restore)
    if snapshot_path == "world":
        events = [event async for event in orchestrator.rollback(row.id, None)]
        assert events[-1].event_type == "complete"
        assert captured[0]["world_roots"] == ["world"]
        assert captured[0]["reference"] is reference
    else:
        with pytest.raises(SelectionResolutionError):
            _ = [event async for event in orchestrator.rollback(row.id, None)]
        assert not captured
