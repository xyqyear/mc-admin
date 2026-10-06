import asyncio
import json
import shutil
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.runtime_resources import current_runtime
from app.servers.models import Server, ServerStatus
from app.servers.references import resolve_server_ref
from app.snapshots.restoration_models import Restoration
from tests.support.restorations import legacy_world_restoration

from .support import complete, create, scope

pytestmark = [
    pytest.mark.binary("restic"),
    pytest.mark.binary("fd"),
    pytest.mark.binary("mcmap"),
]


@pytest.mark.parametrize("source_scope", ["world", "data-root", "outside"])
async def test_legacy_world_history_uses_only_confined_source_roots(
    world_case, tmp_path, source_scope
):
    case = world_case
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_bytes(b"outside data")
    source_path = (
        case.region.parent
        if source_scope == "world"
        else case.data
        if source_scope == "data-root"
        else outside
    )
    source = await case.snapshots.create_snapshot([source_path])
    runtime = current_runtime()
    async with runtime.database.session_factory() as session:
        reference = await resolve_server_ref(
            session, "survival", servers_root=runtime.settings.server_path
        )
    async with runtime.database.session_factory() as session:
        session.add(legacy_world_restoration("legacy", reference, source.id, source.id))
        await session.commit()
    (case.region / "r.0.0.mca").write_bytes(b"live world")
    accepted = await case.commands.rollback("legacy", 1)
    await complete(case, accepted, success=source_scope == "world")
    assert (outside / "keep").read_bytes() == b"outside data"
    if source_scope == "world":
        assert (case.region / "r.0.0.mca").read_bytes() != b"live world"
        row = await case.commands.store.get(accepted["restoration_id"])
        assert json.loads(row.scope_json)["paths"] == [str(case.region.parent)]
    else:
        assert (case.region / "r.0.0.mca").read_bytes() == b"live world"
        assert (
            await case.commands.store.get(accepted["restoration_id"])
        ).safety_snapshot_id is None


async def test_corrupt_absence_record_cannot_remove_sibling_scope(world_case):
    case = world_case
    source = await create(case)
    accepted = await case.commands.restore(scope("dimension"), source, 1)
    await complete(case, accepted)
    sibling = case.data / "other"
    sibling.mkdir()
    (sibling / "keep").write_bytes(b"not selected")
    async with current_runtime().database.session_factory() as session:
        row = await session.get(Restoration, accepted["restoration_id"])
        assert row is not None
        row.selection_json = json.dumps({"absent_parents": [str(sibling)]})
        await session.commit()
    with pytest.raises(HTTPException) as error:
        await case.commands.rollback(accepted["restoration_id"], 1)
    assert error.value.status_code == 409
    assert (sibling / "keep").read_bytes() == b"not selected"


async def test_accepted_world_restore_revalidates_generation_before_writes(
    world_case, monkeypatch
):
    case = world_case
    source = await create(case)
    entered, release = asyncio.Event(), asyncio.Event()
    original = case.commands._planner.revalidate

    async def paused(prepared):
        entered.set()
        await release.wait()
        await original(prepared)

    monkeypatch.setattr(case.commands._planner, "revalidate", paused)
    accepted = await case.commands.restore(scope(), source, 1)
    try:
        await asyncio.wait_for(entered.wait(), 10)
        async with current_runtime().database.session_factory() as session:
            server = await session.scalar(
                select(Server).where(Server.status == ServerStatus.ACTIVE)
            )
            assert server is not None
            server.status = ServerStatus.REMOVED
            server.updated_at = datetime.now(UTC)
            await session.flush()
            session.add(Server(server_id="survival"))
            await session.commit()
        (case.region / "r.0.0.mca").write_bytes(b"replacement world")
    finally:
        release.set()
    await complete(case, accepted, success=False)
    assert (case.region / "r.0.0.mca").read_bytes() == b"replacement world"
    assert (
        await case.commands.store.get(accepted["restoration_id"])
    ).safety_snapshot_id is None


@pytest.mark.parametrize("kind", ["world", "dimension", "regions", "chunks"])
@pytest.mark.parametrize("fault", ["error", "cancel"])
async def test_failed_safety_snapshot_leaves_absent_world_and_server_files_untouched(
    world_case, monkeypatch, kind, fault
):
    case = world_case
    source = await create(case)
    original = await case.commands.restore(scope(kind), source, 1)
    await complete(case, original)
    shutil.rmtree(case.region.parent)
    config = case.data / "config.yml"
    config.write_bytes(b"outside selected world")
    entered = asyncio.Event()

    async def interrupted(*args, **kwargs):
        entered.set()
        if fault == "error":
            raise OSError("controlled safety failure")
        await asyncio.Event().wait()

    monkeypatch.setattr(case.snapshots, "create_snapshot", interrupted)
    accepted = await case.commands.rollback(original["restoration_id"], 1)
    await asyncio.wait_for(entered.wait(), 30)
    if fault == "cancel":
        assert await case.tasks.cancel(accepted["task_id"])
        await asyncio.wait_for(case.tasks.get_future(accepted["task_id"]), 10)
    else:
        await complete(case, accepted, success=False)
    assert not case.region.parent.exists()
    assert config.read_bytes() == b"outside selected world"
    row = await case.commands.store.get(accepted["restoration_id"])
    assert row.safety_snapshot_id is None and row.finished_at
    assert not list(case.data.rglob(".mc-admin-absence-*"))


async def test_invalid_snapshot_absence_evidence_fails_before_safety_or_writes(
    world_case,
):
    case = world_case
    source = await case.snapshots.create_snapshot(
        [case.region.parent], tags=["mc-admin-absence-v1:invalid!"]
    )
    live = case.region / "r.0.0.mca"
    live.write_bytes(b"unchanged live world")
    accepted = await case.commands.restore(scope(), source.id, 1)
    await complete(case, accepted, success=False)
    row = await case.commands.store.get(accepted["restoration_id"])
    assert (
        row
        and row.safety_snapshot_id is None
        and "缺失目录记录无效" in row.error_message
    )
    assert live.read_bytes() == b"unchanged live world"


async def test_history_without_target_identity_remains_readable_but_cannot_offer_rollback(
    world_case,
):
    from app.snapshots.queries import RestorationQueries
    from tests.support.restorations import legacy_world_restoration

    case = world_case
    source = await create(case)
    runtime = current_runtime()
    async with runtime.database.session_factory() as session:
        reference = await resolve_server_ref(
            session, "survival", servers_root=runtime.settings.server_path
        )
        row = legacy_world_restoration("unbound", reference, source, source)
        row.server_generation = None
        row.targets_json = "[]"
        session.add(row)
        await session.commit()
    row = await RestorationQueries(
        runtime.database.session_factory, case.snapshots
    ).get("unbound")
    assert row.source_snapshot_exists and row.safety_snapshot_exists
    assert row.binding_issue == "generation_uncertain"
    assert not row.rollback_available and row.rollback_unavailable_reason
