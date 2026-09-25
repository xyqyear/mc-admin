import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.background_tasks.manager import BackgroundTaskManager
from app.background_tasks.types import TaskProgress, TaskStatus, TaskType
from app.configuration.application import rebuild_server_task
from app.configuration.preparation import ServerConfiguration
from app.db.metadata import Base
from app.errors import INTERNAL_ERROR_MESSAGE
from app.operation_admission import get_server_write_admission
from app.operations.context import (
    OperationExecution,
    bind_execution,
    current_execution,
    mark_cache_degraded,
    record_phase,
)
from app.operations.coordinator import (
    ResourceClaim,
    ResourceKind,
    get_operation_coordinator,
)
from app.operations.journal import InvalidOperationTransition, OperationJournal
from app.operations.journal_types import (
    OperationSpec,
    OperationState,
    ResourceReference,
)
from app.operations.recovery import RecoveryService
from app.servers.models import Server
from app.servers.references import resolve_server_ref

COMPOSE = """services:
  mc:
    container_name: mc-first
    image: itzg/minecraft-server:latest
    environment:
      VERSION: "1.21.8"
    ports:
      - "25565:25565"
      - "25575:25575"
"""


@pytest.fixture
async def configuration_runtime(isolated_runtime):
    async with isolated_runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with isolated_runtime.database.session_factory() as session:
        session.add_all([Server(id=1, server_id="first"), Server(id=2, server_id="other")])
        await session.commit()
    for server in ("first", "other"):
        project = isolated_runtime.settings.server_path / server
        project.mkdir()
        (project / "docker-compose.yml").write_text(COMPOSE)
    journal = OperationJournal(isolated_runtime.database.session_factory)
    isolated_runtime.journal = journal
    recovery = RecoveryService(journal, servers_root=isolated_runtime.settings.server_path)
    isolated_runtime.resources["operation_recovery"] = recovery
    return isolated_runtime, journal, recovery


@pytest.mark.parametrize(("mode", "cancelled"), [
    ("mismatch", False), ("matching", False), ("probe_failure", False), ("mismatch", True),
])
async def test_failed_configuration_reconciles_before_releasing_waiters(configuration_runtime, monkeypatch, caplog, mode, cancelled):
    runtime, journal, recovery = configuration_runtime
    manager = BackgroundTaskManager(journal)
    await journal.accept(OperationSpec("world_restore", (ResourceReference("world", "other", 2),), operation_id="still-running"))
    await journal.start("still-running")
    written, fail_now, verifying, verify_now, waiting, entered = [asyncio.Event() for _ in range(6)]
    original_verify = recovery.configuration_consistent
    verification_count = 0
    secret = "synthetic-configuration-adapter-secret"

    async def verify(record):
        nonlocal verification_count
        verification_count += 1
        verifying.set()
        await verify_now.wait()
        if mode == "probe_failure":
            raise RuntimeError(secret)
        return await original_verify(record)

    async def failed_rebuild(server_id, configuration):
        content = configuration.yaml_content + ("# incomplete target\n" if mode == "mismatch" else "")
        (runtime.settings.server_path / server_id / "docker-compose.yml").write_text(content)
        await record_phase("configuration_written", changed=True)
        written.set()
        await fail_now.wait()
        raise RuntimeError(secret)
        yield TaskProgress(message="unreachable")

    async def waiter():
        waiting.set()
        async with get_operation_coordinator().acquire([ResourceClaim(ResourceKind.MAINTENANCE, "first")]):
            entered.set()

    monkeypatch.setattr(recovery, "configuration_consistent", verify)
    monkeypatch.setattr("app.configuration.application._rebuild_server", failed_rebuild)
    configuration = ServerConfiguration(COMPOSE)
    submitted = await manager.submit_durable(
        TaskType.SERVER_REBUILD, "synthetic-rebuild", rebuild_server_task("first", configuration),
        server_id="first", configuration_version=configuration.fingerprint,
    )
    await asyncio.wait_for(written.wait(), 3)
    waiting_task = asyncio.create_task(waiter())
    try:
        await asyncio.wait_for(waiting.wait(), 3)
        if cancelled:
            assert await manager.cancel(submitted.task_id)
        else:
            fail_now.set()
        await asyncio.wait_for(verifying.wait(), 3)
        pending = await journal.get(submitted.task_id)
        assert pending is not None
        expected_state = OperationState.CANCELLED if cancelled else OperationState.FAILED
        assert pending.state is expected_state
        assert pending.blocked_reason == "configuration_reconciliation_required"
        assert submitted.task_id in {record.operation_id for record in await journal.unsettled()}
        assert get_operation_coordinator().is_occupied(ResourceClaim(ResourceKind.MAINTENANCE, "first"))
        assert not entered.is_set() and not waiting_task.done() and not submitted.awaitable.done()
        get_server_write_admission().check("other")
        assert (await journal.get("still-running")).state is OperationState.RUNNING
        verify_now.set()
        result = await asyncio.wait_for(submitted.awaitable, 3)
        record = await journal.get(submitted.task_id)
        assert record is not None and record.state is expected_state
        assert submitted.task.status is (TaskStatus.CANCELLED if cancelled else TaskStatus.FAILED)
        assert not result.success
        assert result.error == ("已取消" if cancelled else INTERNAL_ERROR_MESSAGE)
        assert record.phase == "configuration_written"
        assert verification_count == 1
        assert secret not in caplog.text
        if mode == "matching":
            await asyncio.wait_for(waiting_task, 3)
            assert entered.is_set() and record.blocked_reason is None
            get_server_write_admission().check("first")
        else:
            with pytest.raises(HTTPException) as conflict:
                await asyncio.wait_for(waiting_task, 3)
            assert conflict.value.status_code == 423
            assert not entered.is_set()
            assert record.blocked_reason == "configuration_reconciliation_required"
            with pytest.raises(HTTPException):
                get_server_write_admission().check("first")
        get_server_write_admission().check("other")
        assert (await journal.get("still-running")).state is OperationState.RUNNING
    finally:
        fail_now.set()
        verify_now.set()
        if not waiting_task.done():
            waiting_task.cancel()
        await asyncio.gather(waiting_task, return_exceptions=True)
        await asyncio.wait_for(submitted.awaitable, 3)
        await journal.finish("still-running", OperationState.SUCCEEDED, writers_stopped=True)


async def test_terminal_reconciliation_refuses_to_interrupt_active_work(journal):
    await journal.accept(OperationSpec("server_rebuild", (ResourceReference("configuration", "first", 1),), operation_id="active"))
    await journal.start("active")
    await journal.phase("active", "configuration_written", changed=True)
    verify = AsyncMock(return_value=False)
    recovery = RecoveryService(journal, configuration_consistent=verify)
    with pytest.raises(InvalidOperationTransition):
        await recovery.reconcile_terminal("active")
    assert (await journal.get("active")).state is OperationState.RUNNING
    verify.assert_not_awaited()


async def test_unconfirmed_live_cache_writer_disables_tiles_without_freezing_server(configuration_runtime):
    from app.routers.servers.map import get_tile

    _, journal, recovery = configuration_runtime
    manager = BackgroundTaskManager(journal)

    async def cache_operation():
        execution = current_execution()
        assert execution is not None
        await journal.set_ownership_known(execution.operation_id, False)
        yield TaskProgress(progress=100)

    submitted = await manager.submit_durable(
        TaskType.CHUNK_PRUNE_PREVIEW, "synthetic-cache", cache_operation(), server_id="first",
    )
    try:
        result = await asyncio.wait_for(submitted.awaitable, 3)
        record = await journal.get(submitted.task_id)
        assert record is not None and record.state is OperationState.INTERRUPTED
        assert not record.writers_stopped and not record.ownership_known
        assert record.cache_degraded and not result.success
        assert submitted.task.status is TaskStatus.FAILED
        assert ResourceReference("cache", "first", 1) in recovery.degraded_resources
        get_server_write_admission().check("first")
        get_server_write_admission().check("other")
        with pytest.raises(HTTPException) as unavailable:
            await get_tile("first", 0, 0, region="world/region")
        assert unavailable.value.status_code == 503
    finally:
        await journal.resolve(submitted.task_id, actor_id=0, writers_stopped=True)


async def test_active_cache_degradation_survives_another_operations_report(configuration_runtime, monkeypatch):
    from app.routers.servers.map import get_tile

    runtime, journal, recovery = configuration_runtime
    await journal.accept(OperationSpec("world_restore", (ResourceReference("world", "first", 1),), operation_id="degraded-active"))
    await journal.start("degraded-active")
    await journal.accept(OperationSpec("world_restore", (ResourceReference("world", "other", 2),), operation_id="unrelated-active"))
    await journal.start("unrelated-active")
    async with journal.session_factory() as session:
        reference = await resolve_server_ref(session, "first", servers_root=runtime.settings.server_path)
    try:
        with bind_execution(OperationExecution(journal, "degraded-active", (reference,))):
            await mark_cache_degraded("first")
        durable = await journal.get("degraded-active")
        assert durable is not None and durable.cache_degraded
        assert durable.state is OperationState.RUNNING
        stale_snapshot = [replace(record, cache_degraded=False) for record in await journal.unsettled()]
        recovery.degraded_resources.add(ResourceReference("cache", "first", 999))
        with monkeypatch.context() as patch:
            patch.setattr(journal, "unsettled", AsyncMock(return_value=stale_snapshot))
            await recovery.report()
        assert any(resource.server_id == "first" and resource.generation == 1 for resource in recovery.degraded_resources)
        assert not any(resource.generation == 999 for resource in recovery.degraded_resources)
        assert (await journal.get("unrelated-active")).state is OperationState.RUNNING
        with pytest.raises(HTTPException) as unavailable:
            await get_tile("first", 0, 0, region="world/region")
        assert unavailable.value.status_code == 503
        get_server_write_admission().check("first")
        get_server_write_admission().check("other")
    finally:
        await journal.finish("degraded-active", OperationState.FAILED, writers_stopped=True)
        await journal.finish("unrelated-active", OperationState.SUCCEEDED, writers_stopped=True)
    assert (await journal.get("degraded-active")).cache_degraded
    with pytest.raises(InvalidOperationTransition):
        await journal.mark_cache_degraded("degraded-active")
