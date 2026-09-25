from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.operation_admission import ServerWriteAdmission
from app.operations.journal_types import (
    OperationSpec,
    OperationState,
    RecoveryReference,
    ResourceReference,
)
from app.operations.recovery import RecoveryService
from app.servers.models import Server, ServerStatus
from app.templates import TemplateSnapshot

WORLD = ResourceReference("world", "survival", 12, "world")
VALID_COMPOSE = """services:
  mc:
    container_name: mc-survival
    image: itzg/minecraft-server:latest
    environment:
      VERSION: "1.21.8"
    ports:
      - "25565:25565"
      - "25575:25575"
"""


async def interrupted(journal, identity="operation", resource=WORLD, **kwargs):
    await journal.accept(OperationSpec("world_restore", (resource,), operation_id=identity, **kwargs))
    await journal.start(identity)
    return await journal.phase(identity, "files_restored", changed=True,
                               recovery_refs=[RecoveryReference("snapshot", "a" * 64)])


async def test_restart_records_interruption_without_replaying_and_keeps_snapshot(journal):
    await interrupted(journal)
    probe, invalidate = AsyncMock(return_value=True), AsyncMock()
    recovery = RecoveryService(journal, probe=probe, validate_resource=AsyncMock(return_value=True), invalidate_cache=invalidate)
    report = await recovery.recover()
    assert report.interrupted_ids == ("operation",)
    assert report.blocks == ()
    assert probe.await_count == 1 and invalidate.await_count == 1
    record = await journal.get("operation")
    assert record is not None
    assert record.state == OperationState.INTERRUPTED
    assert record.phase == "files_restored" and record.data_changed
    assert record.recovery_refs == (RecoveryReference("snapshot", "a" * 64),)
    await recovery.recover()
    assert probe.await_count == 1


async def test_unknown_writer_blocks_only_target_and_cannot_be_forced_clear(journal):
    await interrupted(journal)
    probe = AsyncMock(return_value=False)
    recovery = RecoveryService(journal, probe=probe, validate_resource=AsyncMock(return_value=True))
    await recovery.recover()
    admission = ServerWriteAdmission()
    await recovery.apply_blocks(admission)
    with pytest.raises(HTTPException) as conflict:
        admission.check("survival")
    assert conflict.value.status_code == 423
    admission.check("survival2")
    with pytest.raises(HTTPException) as unresolved:
        await recovery.resolve("operation", actor_id=1, action="acknowledge_partial")
    assert unresolved.value.status_code == 409
    assert (await journal.get("operation")).resolved_at is None


async def test_releasing_one_operation_keeps_other_blocks(journal):
    await interrupted(journal, "first")
    await interrupted(journal, "second")
    probe = AsyncMock(return_value=False)
    recovery = RecoveryService(journal, probe=probe, validate_resource=AsyncMock(return_value=True))
    admission = ServerWriteAdmission()
    await recovery.recover()
    await recovery.apply_blocks(admission)
    probe.return_value = True
    record = await recovery.resolve("first", actor_id=41, action="acknowledge_partial")
    await recovery.apply_blocks(admission)
    assert record.resolved_by == 41
    assert admission.recovery_reason("survival") is not None
    await recovery.resolve("second", actor_id=42, action="acknowledge_partial")
    await recovery.apply_blocks(admission)
    assert admission.recovery_reason("survival") is None


async def test_unknown_global_writer_blocks_conflicting_servers_until_verified(journal):
    await interrupted(journal, resource=ResourceReference("global"))
    recovery = RecoveryService(journal, probe=AsyncMock(return_value=False))
    admission = ServerWriteAdmission()
    await recovery.recover()
    await recovery.apply_blocks(admission)
    for server in ("survival", "creative"):
        with pytest.raises(HTTPException) as conflict:
            admission.check(server)
        assert conflict.value.status_code == 423
    recovery.probe = AsyncMock(return_value=True)
    await recovery.resolve("operation", actor_id=41, action="acknowledge_partial")
    await recovery.apply_blocks(admission)
    admission.check("survival")
    admission.check("creative")


async def test_default_recovery_removes_owned_cache_and_preserves_world(journal, tmp_path):
    root = tmp_path / "servers"
    data = root / "survival/data"
    tiles = data / ".mcmap/tiles"
    tiles.mkdir(parents=True)
    (tiles / "stale.png").write_bytes(b"synthetic-cache")
    (data / "level.dat").write_bytes(b"synthetic-world")
    async with journal.session_factory() as session:
        row = Server(server_id="survival")
        session.add(row)
        await session.commit()
        resource = replace(WORLD, generation=row.id)
    await interrupted(journal, resource=resource)
    report = await RecoveryService(journal, servers_root=root).recover()
    assert report.blocks == () and report.degraded_resources == ()
    assert not tiles.exists()
    assert (data / "level.dat").read_bytes() == b"synthetic-world"


async def test_default_cache_recovery_rejects_nested_symlink_escape(journal, tmp_path):
    root = tmp_path / "servers"
    data = root / "survival/data"
    data.mkdir(parents=True)
    foreign = tmp_path / "unrelated-cache"
    (foreign / "tiles").mkdir(parents=True)
    (foreign / "tiles/keep.png").write_bytes(b"unrelated")
    (data / ".mcmap").symlink_to(foreign, target_is_directory=True)
    async with journal.session_factory() as session:
        row = Server(server_id="survival")
        session.add(row)
        await session.commit()
        resource = replace(WORLD, generation=row.id)
    await interrupted(journal, resource=resource)
    report = await RecoveryService(journal, servers_root=root).recover()
    assert report.blocks == ()
    assert report.degraded_resources == (resource,)
    assert (foreign / "tiles/keep.png").read_bytes() == b"unrelated"


async def test_default_recovery_does_not_touch_same_name_new_generation(journal, tmp_path):
    root = tmp_path / "servers"
    tiles = root / "survival/data/.mcmap/tiles"
    tiles.mkdir(parents=True)
    (tiles / "current.png").write_bytes(b"new-generation")
    async with journal.session_factory() as session:
        old = Server(server_id="survival", status=ServerStatus.REMOVED)
        session.add(old)
        await session.commit()
        old_generation = old.id
        session.add(Server(server_id="survival"))
        await session.commit()
    await interrupted(journal, resource=replace(WORLD, generation=old_generation))
    recovery = RecoveryService(journal, servers_root=root)
    report = await recovery.recover()
    assert report.blocks[0].reason == "target_generation_changed"
    admission = ServerWriteAdmission()
    await recovery.apply_blocks(admission)
    admission.check("survival")
    assert (tiles / "current.png").read_bytes() == b"new-generation"


async def test_default_configuration_resolution_requires_saved_source_equality(journal, tmp_path):
    root = tmp_path / "servers"
    project = root / "survival"
    project.mkdir(parents=True)
    expected = VALID_COMPOSE
    snapshot = TemplateSnapshot(template_id=7, template_name="synthetic-template", yaml_template=expected,
                                variable_definitions=[], snapshot_time="2026-09-25T00:00:00Z")
    async with journal.session_factory() as session:
        row = Server(server_id="survival", template_id=7, template_snapshot_json=snapshot.model_dump_json(), variable_values_json="{}")
        session.add(row)
        await session.commit()
        resource = ResourceReference("configuration", "survival", row.id)
    compose = project / "docker-compose.yml"
    compose.write_text(expected + "# mismatched source\n")
    await journal.accept(OperationSpec("server_rebuild", (resource,), operation_id="configuration"))
    await journal.start("configuration")
    await journal.phase("configuration", "configuration_written", changed=True)
    recovery = RecoveryService(journal, servers_root=root)
    report = await recovery.recover()
    assert report.blocks[0].reason == "configuration_reconciliation_required"
    with pytest.raises(HTTPException) as conflict:
        await recovery.resolve("configuration", actor_id=41, action="configuration_reconciled")
    assert conflict.value.status_code == 409
    compose.write_text(expected)
    record = await recovery.resolve("configuration", actor_id=41, action="configuration_reconciled")
    assert record.blocked_reason is None and record.resolved_by == 41


async def test_direct_configuration_requires_valid_compose_before_resolution(journal, tmp_path):
    root = tmp_path / "servers"
    project = root / "survival"
    project.mkdir(parents=True)
    compose = project / "docker-compose.yml"
    compose.write_text("services: [truncated")
    async with journal.session_factory() as session:
        row = Server(server_id="survival")
        session.add(row)
        await session.commit()
        resource = ResourceReference("configuration", "survival", row.id)
    await journal.accept(OperationSpec("server_rebuild", (resource,), operation_id="direct"))
    await journal.start("direct")
    await journal.phase("direct", "writing_configuration", changed=True)
    recovery = RecoveryService(journal, servers_root=root)
    report = await recovery.recover()
    assert report.blocks[0].reason == "configuration_reconciliation_required"
    with pytest.raises(HTTPException) as conflict:
        await recovery.resolve("direct", actor_id=41, action="configuration_reconciled")
    assert conflict.value.status_code == 409
    compose.write_text(VALID_COMPOSE)
    record = await recovery.resolve("direct", actor_id=41, action="configuration_reconciled")
    assert record.blocked_reason is None


async def test_reused_server_name_does_not_receive_historical_write_or_block(journal):
    await interrupted(journal)
    invalidate = AsyncMock()
    recovery = RecoveryService(journal, probe=AsyncMock(return_value=True),
                               validate_resource=AsyncMock(return_value=False), invalidate_cache=invalidate)
    report = await recovery.recover()
    assert report.blocks[0].reason == "target_generation_changed"
    admission = ServerWriteAdmission()
    await recovery.apply_blocks(admission)
    admission.check("survival")
    invalidate.assert_not_awaited()
    with pytest.raises(HTTPException) as conflict:
        await recovery.resolve("operation", actor_id=1, action="acknowledge_partial")
    assert conflict.value.status_code == 409


async def test_cache_failure_is_durable_degradation_and_does_not_freeze_server(journal):
    await interrupted(journal)
    invalidator = AsyncMock(side_effect=PermissionError("synthetic-cache-permission"))
    recovery = RecoveryService(journal, probe=AsyncMock(return_value=True),
                               validate_resource=AsyncMock(return_value=True), invalidate_cache=invalidator)
    report = await recovery.recover()
    assert report.blocks == ()
    assert report.degraded_resources == (WORLD,)
    assert (await journal.get("operation")).cache_degraded
    admission = ServerWriteAdmission()
    await recovery.apply_blocks(admission)
    admission.check("survival")
    reopened = RecoveryService(journal, validate_resource=AsyncMock(return_value=True), invalidate_cache=AsyncMock())
    report = await reopened.recover()
    assert report.degraded_resources == ()
    assert not (await journal.get("operation")).cache_degraded


async def test_unknown_cache_worker_only_disables_cache(journal):
    cache = replace(WORLD, kind="cache")
    await interrupted(journal, resource=cache)
    recovery = RecoveryService(journal, probe=AsyncMock(return_value=False),
                               validate_resource=AsyncMock(return_value=True))
    report = await recovery.recover()
    assert report.degraded_resources == (cache,)
    admission = ServerWriteAdmission()
    await recovery.apply_blocks(admission)
    admission.check("survival")
    assert not (await journal.get("operation")).writers_stopped


async def test_configuration_inconsistency_requires_verified_reconciliation(journal):
    configuration = ResourceReference("configuration", "survival", 12)
    await journal.accept(OperationSpec("server_rebuild", (configuration,), operation_id="rebuild"))
    await journal.start("rebuild")
    await journal.phase("rebuild", "configuration_written", changed=True)
    consistent = AsyncMock(return_value=False)
    recovery = RecoveryService(journal, probe=AsyncMock(return_value=True),
                               validate_resource=AsyncMock(return_value=True), configuration_consistent=consistent)
    report = await recovery.recover()
    assert report.blocks[0].reason == "configuration_reconciliation_required"
    with pytest.raises(HTTPException):
        await recovery.resolve("rebuild", actor_id=1, action="configuration_reconciled")
    consistent.return_value = True
    with pytest.raises(HTTPException):
        await recovery.resolve("rebuild", actor_id=1, action="acknowledge_partial")
    record = await recovery.resolve("rebuild", actor_id=1, action="configuration_reconciled")
    assert record.blocked_reason is None and record.data_changed


async def test_probe_failure_does_not_expose_error_or_allow_writes(journal):
    await interrupted(journal)
    recovery = RecoveryService(journal, probe=AsyncMock(side_effect=RuntimeError("synthetic-secret")),
                               validate_resource=AsyncMock(return_value=True))
    report = await recovery.recover()
    assert report.blocks[0].reason == "writers_unconfirmed"
    assert "synthetic-secret" not in str(await journal.get("operation"))
