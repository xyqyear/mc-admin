import asyncio
import threading

import pytest
from fastapi import HTTPException

from app.configuration import files
from app.configuration.preparation import (
    ServerConfiguration,
    prepare_template_configuration,
)
from app.errors import INTERNAL_ERROR_MESSAGE
from app.minecraft import MCServerStatus
from app.operation_admission import get_server_write_admission
from app.operations.journal_types import (
    OperationSpec,
    OperationState,
    RecoveryReference,
    ResourceReference,
)
from app.templates import StringVariableDefinition, TemplateSnapshot
from app.world.locks import get_server_operation_lock

from .conftest import COMPOSE


def template_configuration():
    return prepare_template_configuration(TemplateSnapshot(
        template_id=42, template_name="保留快照", snapshot_time="2026-09-25T00:00:00Z",
        yaml_template=COMPOSE.replace('MEMORY: "2G"', 'MEMORY: "{memory}"'),
        variable_definitions=[StringVariableDefinition(name="memory", display_name="内存")],
    ), {"memory": "3G"})


@pytest.mark.parametrize(("phase", "written", "source_saved", "started"), [
    ("configuration_prepared", False, False, False),
    ("staging_configuration", False, False, False),
    ("configuration_staged", False, False, False),
    ("stopping_server", False, False, False),
    ("server_stopped", False, False, False),
    ("writing_configuration", False, False, False),
    ("configuration_written", True, False, False),
    ("saving_configuration_source", True, False, False),
    ("configuration_source_saved", True, True, False),
    ("starting_server", True, True, False),
    ("server_started", True, True, True),
])
async def test_failures_at_durable_boundaries_retain_truth(configuration, monkeypatch, phase, written, source_saved, started):
    configuration.status.return_value = MCServerStatus.HEALTHY
    original = configuration.journal.phase

    async def fail_at_boundary(operation_id, current_phase, **kwargs):
        result = await original(operation_id, current_phase, **kwargs)
        if current_phase == phase:
            raise RuntimeError("synthetic-private-adapter-error")
        return result

    monkeypatch.setattr(configuration.journal, "phase", fail_at_boundary)
    target = template_configuration()
    submitted = await configuration.submit(target)
    result = await submitted.awaitable
    assert not result.success and result.error == INTERNAL_ERROR_MESSAGE
    current = await configuration.state()
    assert current.yaml_content == (target.yaml_content if written else COMPOSE)
    assert current.template_id == (42 if source_saved else None)
    assert configuration.up.await_count == int(started)
    assert not list(configuration.compose.parent.glob(".mc-admin-configuration-*.tmp"))
    record = await configuration.journal.get(submitted.task_id)
    assert record is not None and record.state == OperationState.FAILED
    assert record.running_intent is True
    assert record.phase == phase
    assert all(ref.resolved for ref in record.recovery_refs)
    assert (record.blocked_reason is not None) == (written and not source_saved)
    assert bool(get_server_write_admission().recovery_reason("first")) == (written and not source_saved)


@pytest.mark.parametrize("status", [MCServerStatus.EXISTS, MCServerStatus.CREATED, MCServerStatus.HEALTHY])
async def test_success_preserves_running_intent_and_matching_source(configuration, status):
    configuration.status.return_value = status
    target = template_configuration()
    submitted = await configuration.submit(target)
    result = await submitted.awaitable
    assert result.success
    current = await configuration.state()
    assert current.yaml_content == target.yaml_content
    assert current.snapshot_json == target.snapshot_json
    assert current.values_json == target.values_json
    assert configuration.down.await_count == int(status != MCServerStatus.EXISTS)
    assert configuration.up.await_count == int(status == MCServerStatus.HEALTHY)
    assert result.data is not None and result.data["version"] == current.version


@pytest.mark.parametrize("invalid", ["different_server", "created_container"])
async def test_validation_prevents_replacing_wrong_or_live_server(configuration, invalid):
    content = COMPOSE.replace("mc-first", "mc-other") if invalid == "different_server" else COMPOSE
    configuration.created.return_value = invalid == "created_container"
    submitted = await configuration.submit(ServerConfiguration(content))
    assert not (await submitted.awaitable).success
    assert configuration.compose.read_text() == COMPOSE
    configuration.up.assert_not_awaited()


@pytest.mark.parametrize("boundary", ["stage", "replace"])
async def test_cancellation_waits_for_file_worker_and_recovery_before_releasing_lease(configuration, monkeypatch, boundary):
    original = files._write_stage if boundary == "stage" else files._replace
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    released = threading.Event()

    def slow_worker(*args):
        original(*args)
        loop.call_soon_threadsafe(entered.set)
        if not released.wait(10):
            raise TimeoutError("test did not release file worker")

    monkeypatch.setattr(files, "_write_stage" if boundary == "stage" else "_replace", slow_worker)
    submitted = await configuration.submit(template_configuration())
    try:
        await asyncio.wait_for(entered.wait(), 3)
        assert await configuration.tasks.cancel(submitted.task_id)
        assert not submitted.awaitable.done()
        assert get_server_operation_lock().is_locked("first")
        released.set()
        assert not (await asyncio.wait_for(submitted.awaitable, 3)).success
    finally:
        released.set()
    assert not list(configuration.compose.parent.glob(".mc-admin-configuration-*.tmp"))
    assert configuration.compose.read_text() == (COMPOSE if boundary == "stage" else template_configuration().yaml_content)
    record = await configuration.journal.get(submitted.task_id)
    assert record is not None and record.state == OperationState.CANCELLED and record.writers_stopped
    assert bool(record.blocked_reason) == (boundary == "replace")


async def test_metadata_commit_failure_keeps_source_and_supports_explicit_baseline_recovery(configuration, monkeypatch):
    from app.configuration.application import save_configuration_metadata

    baseline = await configuration.state()

    async def flush_then_fail(db, server_id, prepared, **kwargs):
        await save_configuration_metadata(db, server_id, prepared, **kwargs)
        raise RuntimeError("private")

    monkeypatch.setattr("app.configuration.application.save_configuration_metadata", flush_then_fail)
    submitted = await configuration.submit(template_configuration())
    assert not (await submitted.awaitable).success
    assert (await configuration.state()).template_id is None
    with pytest.raises(HTTPException):
        await configuration.recovery.resolve(submitted.task_id, actor_id=0, action="configuration_reconciled")
    configuration.compose.write_bytes(baseline.content)
    resolved = await configuration.recovery.resolve(submitted.task_id, actor_id=0, action="configuration_reconciled")
    assert resolved.blocked_reason is None
    configuration.up.assert_not_awaited()


async def test_restart_cleans_only_owned_staging_file_without_replaying(configuration):
    token = "a" * 32
    owned = files.stage_path(configuration.compose.parent, token)
    other = files.stage_path(configuration.compose.parent, "b" * 32)
    owned.write_text("pending")
    other.write_text("unrelated")
    baseline = await configuration.state()
    await configuration.journal.accept(OperationSpec("configuration_apply", (ResourceReference("configuration", "first", 1),), operation_id="crashed", configuration_version=ServerConfiguration(COMPOSE).fingerprint))
    await configuration.journal.start("crashed")
    await configuration.journal.phase("crashed", "staging_configuration", recovery_refs=(
        RecoveryReference("configuration_stage", token),
        RecoveryReference("configuration_baseline", baseline.version, resolved=True),
    ))
    report = await configuration.recovery.recover()
    assert report.interrupted_ids == ("crashed",)
    assert not report.blocks and not owned.exists() and other.read_text() == "unrelated"
    configuration.up.assert_not_awaited()
    assert configuration.compose.read_text() == COMPOSE


async def test_staging_is_private_before_permissions_are_restored(configuration, monkeypatch):
    configuration.compose.chmod(0o600)
    original = files.os.fchown
    observed = []

    def observe_permissions(fd, uid, gid):
        observed.append(files.os.fstat(fd).st_mode & 0o777)
        return original(fd, uid, gid)

    monkeypatch.setattr(files.os, "fchown", observe_permissions)
    async with files.staged_configuration(configuration.compose, ("# secret\n" * 9000).encode()) as staged:
        assert staged.stage.stat().st_mode & 0o777 == 0o600
    assert observed == [0o600]


async def test_terminal_staging_cleanup_failure_is_retried_on_startup(configuration, monkeypatch):
    from pathlib import Path

    original = Path.unlink
    blocked = True

    def refuse_owned_stage(path, *args, **kwargs):
        if path.name.startswith(".mc-admin-configuration-") and blocked:
            raise PermissionError("synthetic private cleanup failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", refuse_owned_stage)
    submitted = await configuration.submit(template_configuration())
    assert not (await submitted.awaitable).success
    retained = await configuration.journal.unsettled()
    assert any(record.operation_id == submitted.task_id for record in retained)
    blocked = False
    await configuration.recovery.recover()
    assert not list(configuration.compose.parent.glob(".mc-admin-configuration-*.tmp"))
    record = await configuration.journal.get(submitted.task_id)
    assert record is not None and all(reference.resolved for reference in record.recovery_refs)
    assert not await configuration.journal.unsettled()


async def test_interruption_before_first_change_does_not_require_target_configuration(configuration):
    await configuration.journal.accept(OperationSpec(
        "server_rebuild", (ResourceReference("configuration", "first", 1),),
        operation_id="before-preparation", configuration_version=template_configuration().fingerprint,
    ))
    await configuration.journal.start("before-preparation")
    report = await configuration.recovery.recover()
    assert report.interrupted_ids == ("before-preparation",)
    assert not report.blocks
    assert configuration.compose.read_text() == COMPOSE
    assert (await configuration.recovery.resolve("before-preparation", actor_id=0, action="configuration_reconciled")).blocked_reason is None
    configuration.up.assert_not_awaited()


async def test_failed_atomic_replace_preserves_original_and_cleans_stage(configuration, monkeypatch):
    def cannot_replace(*_):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(files.os, "replace", cannot_replace)
    submitted = await configuration.submit(template_configuration())
    assert not (await submitted.awaitable).success
    assert configuration.compose.read_text() == COMPOSE
    assert (await configuration.state()).template_id is None
    assert not list(configuration.compose.parent.glob(".mc-admin-configuration-*.tmp"))
    record = await configuration.journal.get(submitted.task_id)
    assert record is not None and record.blocked_reason is None
    configuration.up.assert_not_awaited()


async def test_internal_compose_link_stages_beside_its_target(configuration, monkeypatch):
    project = configuration.compose.parent
    nested = project / "source"
    nested.mkdir()
    target = nested / "actual.yml"
    configuration.compose.rename(target)
    configuration.compose.symlink_to(target.relative_to(project))
    original = files._replace
    placements = []

    def observe_replace(stage, destination):
        placements.append((stage.parent, destination.parent))
        original(stage, destination)

    monkeypatch.setattr(files, "_replace", observe_replace)
    submitted = await configuration.submit(template_configuration())
    assert (await submitted.awaitable).success
    assert placements == [(nested, nested)]
    assert configuration.compose.is_symlink()
    assert target.read_text() == template_configuration().yaml_content
    record = await configuration.journal.get(submitted.task_id)
    assert record is not None
    artifact = next(resource for resource in record.resources if resource.kind == "configuration_stage")
    assert artifact.path.startswith("source/.mc-admin-configuration-")


async def test_stage_recovery_uses_retained_path_when_compose_link_changes(configuration):
    project = configuration.compose.parent
    nested = project / "source"
    nested.mkdir()
    token = "c" * 32
    owned = files.stage_path(nested, token)
    owned.write_text("private stage")
    await configuration.journal.accept(OperationSpec("server_rebuild", (ResourceReference("configuration", "first", 1),), operation_id="retained-path"))
    await configuration.journal.start("retained-path")
    await configuration.journal.retain_artifact("retained-path", ResourceReference("configuration_stage", "first", 1, owned.relative_to(project).as_posix()))
    await configuration.journal.phase("retained-path", "staging_configuration", recovery_refs=(RecoveryReference("configuration_stage", token),))
    report = await configuration.recovery.recover()
    assert not report.blocks and not owned.exists()
    assert configuration.compose.read_text() == COMPOSE


@pytest.mark.parametrize("command", ["down", "up"])
async def test_daemon_failure_is_durable_and_never_automatically_replayed(configuration, command):
    configuration.status.return_value = MCServerStatus.HEALTHY
    getattr(configuration, command).side_effect = RuntimeError("synthetic private Docker error")
    submitted = await configuration.submit(template_configuration())
    assert not (await submitted.awaitable).success
    record = await configuration.journal.get(submitted.task_id)
    assert record is not None and record.state == OperationState.INTERRUPTED
    assert record.running_intent and record.blocked_reason == "writers_unconfirmed"
    assert configuration.compose.read_text() == (COMPOSE if command == "down" else template_configuration().yaml_content)
    before = configuration.down.await_count, configuration.up.await_count
    await configuration.recovery.recover()
    assert (configuration.down.await_count, configuration.up.await_count) == before
    settled = await configuration.journal.get(submitted.task_id)
    assert settled is not None and settled.blocked_reason is None


async def test_recovery_does_not_follow_retargeted_stage_parent(configuration, tmp_path):
    project = configuration.compose.parent
    token = "d" * 32
    outside = tmp_path / "unrelated"
    outside.mkdir()
    unrelated = files.stage_path(outside, token)
    unrelated.write_text("do not delete")
    (project / "source").symlink_to(outside, target_is_directory=True)
    await configuration.journal.accept(OperationSpec("server_rebuild", (ResourceReference("configuration", "first", 1),), operation_id="retargeted-stage"))
    await configuration.journal.start("retargeted-stage")
    await configuration.journal.retain_artifact("retargeted-stage", ResourceReference("configuration_stage", "first", 1, f"source/{unrelated.name}"))
    await configuration.journal.phase("retargeted-stage", "staging_configuration", recovery_refs=(RecoveryReference("configuration_stage", token),))
    await configuration.recovery.recover()
    assert unrelated.read_text() == "do not delete"
    retained = await configuration.journal.get("retargeted-stage")
    assert retained is not None
    assert any(not reference.resolved for reference in retained.recovery_refs)
    assert retained.writers_stopped and retained.blocked_reason is None


async def test_recovery_does_not_clean_artifact_from_reused_server_name(configuration):
    from app.servers.models import Server, ServerStatus

    token = "e" * 32
    unrelated = files.stage_path(configuration.compose.parent, token)
    unrelated.write_text("new instance artifact")
    await configuration.journal.accept(OperationSpec("server_rebuild", (ResourceReference("configuration", "first", 1),), operation_id="old-instance"))
    await configuration.journal.start("old-instance")
    await configuration.journal.phase("old-instance", "staging_configuration", recovery_refs=(RecoveryReference("configuration_stage", token),))
    async with configuration.journal.session_factory() as db:
        old = await db.get(Server, 1)
        assert old is not None
        old.status = ServerStatus.REMOVED
        await db.flush()
        db.add(Server(server_id="first"))
        await db.commit()
    report = await configuration.recovery.recover()
    assert report.blocks[0].reason == "target_generation_changed"
    assert unrelated.read_text() == "new instance artifact"
