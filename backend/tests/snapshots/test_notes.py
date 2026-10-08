import pytest
from pydantic import ValidationError

from app.runtime_resources import current_runtime
from app.snapshots.api_models import CreateSnapshotRequest, UpdateSnapshotNoteRequest
from app.snapshots.notes import SnapshotNotes
from app.snapshots.scopes import GlobalScope, PathsScope
from app.snapshots.service import SnapshotService

from .support import complete


@pytest.mark.binary("restic")
async def test_created_notes_survive_service_reconstruction_without_changing_identity(case):
    target = case.data / "settings.txt"
    target.write_text("original")
    scope = PathsScope(server_id="survival", paths=("settings.txt",))
    created = await complete(case, await case.commands.create(scope, 1, "升级前的中文备注"))
    snapshot_id = created["snapshot"]["id"]
    assert created["snapshot"]["note"] == "升级前的中文备注"
    assert created["note_warning"] is None
    original = await case.client.get_snapshot(snapshot_id)
    await case.snapshots.save_note(snapshot_id, "升级后的中文备注")
    reconstructed = SnapshotService(
        case.client, current_runtime().docker_mc_manager,
        SnapshotNotes(current_runtime().database.session_factory),
    )
    persisted = await reconstructed.get_snapshot(snapshot_id)
    assert persisted.id == snapshot_id and persisted.note == "升级后的中文备注"
    assert persisted.paths == original.paths and persisted.tags == original.tags
    assert [item.note for item in await reconstructed.list_snapshots()] == ["升级后的中文备注"]
    assert (await case.commands.eligible(scope))[0].note == "升级后的中文备注"
    await reconstructed.save_note(snapshot_id, "")
    assert (await reconstructed.get_snapshot(snapshot_id)).note == ""


@pytest.mark.binary("restic")
async def test_note_save_failure_returns_created_snapshot_and_only_note_retry(case, monkeypatch):
    target = case.data / "settings.txt"
    target.write_text("original")
    save = case.snapshots.save_note

    async def unavailable(*args):
        raise OSError("metadata unavailable")

    monkeypatch.setattr(case.snapshots, "save_note", unavailable)
    scope = PathsScope(server_id="survival", paths=("settings.txt",))
    result = await complete(case, await case.commands.create(scope, 1, "需要重试的备注"))
    snapshot_id = result["snapshot"]["id"]
    assert result["snapshot"]["note"] == ""
    assert "快照已创建" in result["note_warning"]
    assert [item.id for item in await case.snapshots.list_snapshots()] == [snapshot_id]
    monkeypatch.setattr(case.snapshots, "save_note", save)
    await case.snapshots.save_note(snapshot_id, "需要重试的备注")
    snapshots = await case.snapshots.list_snapshots()
    assert len(snapshots) == 1 and snapshots[0].note == "需要重试的备注"


@pytest.mark.binary("restic")
async def test_source_excluding_one_selected_root_skips_it_and_allows_other_roots(case):
    folder = case.data / "config"
    folder.mkdir()
    (folder / "public.txt").write_text("source")
    (folder / "private.txt").write_text("private source")
    other = case.data / "other.txt"
    other.write_text("other")
    case.config.snapshots.ignored_paths = ["config/private.txt"]
    source = await case.snapshots.create_snapshot([folder, other])
    case.config.snapshots.ignored_paths = []
    mixed = PathsScope(server_id="survival", paths=("other.txt", "config/private.txt"))
    candidates = await case.commands.eligible(mixed)
    assert [item.id for item in candidates] == [source.id]
    assert candidates[0].skipped_paths == [str(folder / "private.txt")]
    assert candidates[0].skipped_count == 1
    allowed = PathsScope(server_id="survival", paths=("config", "other.txt"))
    assert [item.id for item in await case.commands.eligible(allowed)] == [source.id]
    (folder / "public.txt").write_text("before restore")
    (folder / "private.txt").write_text("protected live")
    other.write_text("other live")
    result = await case.commands.restore(allowed, source.id, 1)
    await complete(case, result)
    assert (folder / "public.txt").read_text() == "source"
    assert (folder / "private.txt").read_text() == "protected live"
    assert other.read_text() == "other"


async def test_notes_are_isolated_by_repository_and_full_snapshot_identity(tmp_path):
    from app.db.database import Database
    from app.db.metadata import Base

    database = Database(f"sqlite:///{tmp_path / 'notes.db'}")
    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        notes = SnapshotNotes(database.session_factory)
        snapshot = "a" * 64
        await notes.save("1" * 64, snapshot, "仓库一")
        await notes.save("2" * 64, snapshot, "仓库二")
        await notes.save("1" * 64, "a" * 63 + "b", "另一快照")
        assert await notes.read("1" * 64, [snapshot, "a" * 63 + "b"]) == {
            snapshot: "仓库一", "a" * 63 + "b": "另一快照",
        }
        assert await notes.read("2" * 64, [snapshot]) == {snapshot: "仓库二"}
        with pytest.raises(ValueError):
            await notes.save("1" * 64, snapshot, "字" * 501)
        assert await notes.read("1" * 64, [snapshot]) == {snapshot: "仓库一"}
    finally:
        await database.close()


def test_note_request_limits_count_unicode_characters():
    assert UpdateSnapshotNoteRequest(note="😀" * 500).note == "😀" * 500
    with pytest.raises(ValidationError):
        UpdateSnapshotNoteRequest(note="字" * 501)
    with pytest.raises(ValidationError):
        CreateSnapshotRequest(scope=GlobalScope(), note="字" * 501)


@pytest.mark.binary("restic")
async def test_notes_follow_real_repository_identity_across_relocation_and_reinitialization(case):
    from pathlib import Path

    from app.snapshots.restic import ResticClient
    from app.utils.exec import exec_command

    target = case.data / "settings.txt"
    target.write_text("original")
    created = await complete(case, await case.commands.create(
        PathsScope(server_id="survival", paths=("settings.txt",)), 1, "原仓库的备注"
    ))
    snapshot_id = created["snapshot"]["id"]
    repository_id = await case.client.repository_id()
    location = Path(case.client.repository_path)
    moved = location.with_name("moved-repository")
    location.rename(moved)
    relocated = ResticClient(str(moved), password="command-test")
    assert await relocated.repository_id() == repository_id
    notes = SnapshotNotes(current_runtime().database.session_factory)
    service = SnapshotService(relocated, current_runtime().docker_mc_manager, notes)
    assert (await service.get_snapshot(snapshot_id)).note == "原仓库的备注"
    await exec_command(str(case.client.binary_path), "init", env=case.client.env)
    replacement_id = await case.client.repository_id()
    assert replacement_id != repository_id
    assert await notes.read(replacement_id, [snapshot_id]) == {}
    assert await notes.read(repository_id, [snapshot_id]) == {snapshot_id: "原仓库的备注"}
