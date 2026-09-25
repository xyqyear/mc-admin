import pytest

from app.db.metadata import Base
from app.operations.context import OperationExecution, bind_execution
from app.operations.journal import OperationJournal
from app.operations.journal_types import (
    OperationSpec,
    OperationState,
    ResourceReference,
)
from app.world.artifacts import reap_restore_stages, restore_stage


async def test_restore_stage_reaper_rechecks_active_after_directory_listing(monkeypatch):
    from app.world import artifacts

    base = artifacts.artifact_root("restore-stage")
    base.mkdir(parents=True, exist_ok=True)
    original = artifacts.async_fs.iterdir
    context = restore_stage()
    stages = []

    async def list_after_creation(path):
        stages.append(await context.__aenter__())
        return await original(path)

    monkeypatch.setattr(artifacts.async_fs, "iterdir", list_after_creation)
    try:
        await reap_restore_stages()
        assert stages[0].exists()
    finally:
        await context.__aexit__(None, None, None)
    assert not stages[0].exists()


async def test_restore_stage_reaper_rechecks_journal_before_each_deletion(monkeypatch):
    from app.world import artifacts

    base = artifacts.artifact_root("restore-stage")
    first, retained = base / ("a" * 32), base / ("b" * 32)
    first.mkdir(parents=True)
    retained.mkdir()
    protected = set()
    original = artifacts.async_fs.rmtree

    async def protection(_kind):
        return set(protected)

    async def remove_first(path, **kwargs):
        await original(path, **kwargs)
        protected.add(retained.name)

    async def ordered_listing(_base):
        return [first, retained]

    monkeypatch.setattr(artifacts, "protected_artifacts", protection)
    monkeypatch.setattr(artifacts.async_fs, "iterdir", ordered_listing)
    monkeypatch.setattr(artifacts.async_fs, "rmtree", remove_first)
    await reap_restore_stages()
    assert not first.exists()
    assert retained.exists()
    await original(retained)


async def test_restore_stage_survives_unconfirmed_writer_and_restart_cleanup(isolated_runtime):
    runtime = isolated_runtime
    async with runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    journal = OperationJournal(runtime.database.session_factory)
    runtime.journal = journal
    record = await journal.accept(OperationSpec(kind="world_restore", resources=(ResourceReference("world", "srv1", 1),)))
    await journal.start(record.operation_id)
    with bind_execution(OperationExecution(journal, record.operation_id)):
        async with restore_stage() as stage:
            (stage / "source.mca").write_bytes(b"retained source")
            await journal.set_ownership_known(record.operation_id, False)
            await reap_restore_stages()
            assert stage.is_dir()
    await journal.finish(record.operation_id, OperationState.INTERRUPTED, writers_stopped=False)
    await reap_restore_stages()
    assert (stage / "source.mca").read_bytes() == b"retained source"
    retained = await journal.get(record.operation_id)
    assert retained is not None
    assert any(ref.kind == "world_restore_stage" and not ref.resolved for ref in retained.recovery_refs)
    await journal.resolve(record.operation_id, actor_id=1, writers_stopped=True)
    await reap_restore_stages()
    assert not runtime.resources["world_restore_stages"]
    assert stage.exists()
    await journal.resolve(record.operation_id, actor_id=1, writers_stopped=True, resolve_references=True)
    await reap_restore_stages()
    assert not stage.exists()


async def test_restore_stage_is_removed_after_known_failure():
    stage = None
    with pytest.raises(RuntimeError):
        async with restore_stage() as stage:
            (stage / "source.mca").write_bytes(b"owned source")
            raise RuntimeError("controlled restore failure")
    assert stage is not None
    assert not stage.exists()
