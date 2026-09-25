import asyncio
from contextlib import aclosing, asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.auth.schemas import UserPublic
from app.cron import crud
from app.cron.jobs import restart
from app.cron.manager import CronManager
from app.cron.models import ExecutionStatus
from app.db.metadata import Base
from app.minecraft import MCServerStatus
from app.operation_admission import get_server_write_admission
from app.operations.context import current_execution
from app.operations.coordinator import (
    ResourceClaim,
    ResourceKind,
    get_operation_coordinator,
)
from app.operations.journal import OperationJournal
from app.operations.journal_types import (
    OperationSpec,
    OperationState,
    ResourceReference,
)
from app.operations.recovery import RecoveryService
from app.routers.servers import operations
from app.servers.models import Server
from app.world.locks import ServerOperationLock
from app.world.models import RestorationType
from app.world.restore import WorldRestoreOrchestrator
from app.world.schemas import RestorationSelection
from tests.support.runtime import set_runtime_resource


@pytest.fixture
async def daemon_runtime(isolated_runtime, monkeypatch):
    runtime = isolated_runtime
    async with runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with runtime.database.session_factory() as session:
        session.add_all([Server(id=1, server_id="first"), Server(id=2, server_id="other")])
        await session.commit()
        await crud.create_cronjob(
            session, cronjob_id="scheduled-restart", identifier="restart_server",
            name="重启", cron="0 0 * * *", params_json='{"server_id":"first"}',
        )
    for server_id in ("first", "other"):
        project = runtime.settings.server_path / server_id
        project.mkdir()
        (project / "docker-compose.yml").write_text("services: {}\n")
    journal = OperationJournal(runtime.database.session_factory)
    runtime.journal = journal
    recovery = RecoveryService(journal, servers_root=runtime.settings.server_path)
    runtime.resources["operation_recovery"] = recovery
    lock = ServerOperationLock(get_operation_coordinator())
    runtime.resources["server_operation_lock"] = lock
    instance = SimpleNamespace(
        exists=AsyncMock(return_value=True), running=AsyncMock(return_value=True),
        get_status=AsyncMock(return_value=MCServerStatus.CREATED), created=AsyncMock(return_value=True),
        start=AsyncMock(), up=AsyncMock(), restart=AsyncMock(), stop=AsyncMock(), down=AsyncMock(),
    )
    manager = Mock(get_instance=Mock(return_value=instance))
    set_runtime_resource(monkeypatch, 'docker_mc_manager', manager)
    user = UserPublic(id=17, username="operator", created_at=datetime.now(UTC))

    async def manual(action):
        async with runtime.database.session_factory() as session:
            return await operations.server_operation("first", operations.ServerOperation(action=action), session, user)

    context = SimpleNamespace(
        runtime=runtime, journal=journal, recovery=recovery, lock=lock,
        instance=instance, manager=manager, manual=manual, cron=CronManager(),
    )
    try:
        yield context
    finally:
        for record in await journal.unsettled():
            await journal.resolve(record.operation_id, actor_id=0, writers_stopped=True)


@pytest.mark.parametrize(("action", "phase", "intent"), [
    ("up", "server_started", True), ("start", "server_started", True),
    ("restart", "server_restarted", True), ("stop", "server_stopped", False),
    ("down", "server_down", False),
])
async def test_manual_lifecycle_preserves_response_and_durable_history(daemon_runtime, action, phase, intent):
    env = daemon_runtime

    async def command():
        execution = current_execution()
        assert execution is not None
        pending = await env.journal.get(execution.operation_id)
        assert pending.state is OperationState.RUNNING
        assert not pending.ownership_known and not pending.writers_stopped
        assert pending.running_intent is intent

    getattr(env.instance, action).side_effect = command
    assert await env.manual(action) == {"message": f"Server 'first' {action} operation completed"}
    [record] = await env.journal.list()
    assert record.kind == f"server_{action}" and record.phase == phase
    assert record.origin == "request" and record.actor_id == 17 and record.legacy_id is None
    assert record.state is OperationState.SUCCEEDED and record.writers_stopped and record.ownership_known
    assert record.running_intent is intent
    assert record.resources == (ResourceReference("server", "first", 1),)
    get_server_write_admission().check("first")


@pytest.mark.parametrize("action", ["stop", "down"])
async def test_stop_and_down_remain_available_without_clearing_another_block(daemon_runtime, action):
    env = daemon_runtime
    await env.journal.accept(OperationSpec("server_restart", (ResourceReference("server", "first", 1),), operation_id="uncertain"))
    await env.journal.start("uncertain")
    await env.journal.set_ownership_known("uncertain", False)
    await env.journal.finish("uncertain", OperationState.INTERRUPTED, writers_stopped=False)
    await env.recovery.apply_blocks(get_server_write_admission())
    with pytest.raises(HTTPException) as blocked:
        await env.manual("start")
    assert blocked.value.status_code == 423
    env.instance.start.assert_not_awaited()
    await env.manual(action)
    getattr(env.instance, action).assert_awaited_once()
    with pytest.raises(HTTPException) as still_blocked:
        get_server_write_admission().check("first")
    assert still_blocked.value.status_code == 423
    get_server_write_admission().check("other")
    current = [record for record in await env.journal.list() if record.kind == f"server_{action}"]
    assert len(current) == 1 and current[0].state is OperationState.SUCCEEDED


@pytest.mark.parametrize("action", ["start", "up", "restart", "cron"])
async def test_cancelled_cli_cannot_release_restore_before_daemon_block(daemon_runtime, monkeypatch, action):
    env = daemon_runtime
    command_entered, daemon_release, late_started, settling, settle_now, restore_waiting = [asyncio.Event() for _ in range(6)]
    daemon_tasks = []
    operation_ids = []
    original_finish = env.journal.finish
    original_acquire = ServerOperationLock.lease

    async def daemon_continues():
        await daemon_release.wait()
        env.instance.get_status.return_value = MCServerStatus.RUNNING
        late_started.set()

    async def cli_command():
        execution = current_execution()
        assert execution is not None
        operation_ids.append(execution.operation_id)
        assert not (await env.journal.get(execution.operation_id)).ownership_known
        daemon_tasks.append(asyncio.create_task(daemon_continues()))
        command_entered.set()
        await asyncio.Event().wait()

    async def finish(operation_id, state, **kwargs):
        if operation_id in operation_ids:
            settling.set()
            await settle_now.wait()
        return await original_finish(operation_id, state, **kwargs)

    @asynccontextmanager
    async def acquire(lock, server_ids, holder, **kwargs):
        if holder.kind.value == "restore":
            restore_waiting.set()
        async with original_acquire(lock, server_ids, holder, **kwargs) as lease:
            yield lease

    monkeypatch.setattr(env.journal, "finish", finish)
    monkeypatch.setattr(ServerOperationLock, "lease", acquire)
    getattr(env.instance, "restart" if action == "cron" else action).side_effect = cli_command
    snapshots = Mock(create_snapshot=AsyncMock())
    orchestrator = WorldRestoreOrchestrator(
        snapshot_service=snapshots, docker_mc_manager=env.manager, server_operation_lock=env.lock,
        session_factory=env.runtime.database.session_factory,
        preview_base_dir=env.runtime.settings.server_path / "previews",
    )

    async def restore():
        async with aclosing(orchestrator.begin_restore(
            "first", "source", RestorationSelection(type=RestorationType.WORLD), user_id=17,
        )) as events:
            await anext(events)

    if action == "cron":
        operation = env.cron._execute_cronjob_wrapper(
            "scheduled-restart", "restart_server", restart.ServerRestartParams(server_id="first"),
            restart.restart_server_cronjob,
        )
    else:
        operation = env.manual(action)
    worker = asyncio.create_task(operation)
    restore_task = None
    try:
        await asyncio.wait_for(command_entered.wait(), 3)
        restore_task = asyncio.create_task(restore())
        await asyncio.wait_for(restore_waiting.wait(), 3)
        worker.cancel()
        await asyncio.wait_for(settling.wait(), 3)
        assert get_operation_coordinator().is_occupied(ResourceClaim(ResourceKind.MAINTENANCE, "first"))
        assert not worker.done() and not restore_task.done()
        env.instance.get_status.assert_not_awaited()
        snapshots.create_snapshot.assert_not_awaited()
        get_server_write_admission().check("other")
        settle_now.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(worker, 3)
        with pytest.raises(HTTPException) as blocked:
            await asyncio.wait_for(restore_task, 3)
        assert blocked.value.status_code == 423
        assert not late_started.is_set()
        daemon_release.set()
        await asyncio.wait_for(late_started.wait(), 3)
        env.instance.get_status.assert_not_awaited()
        snapshots.create_snapshot.assert_not_awaited()
        record = await env.journal.get(operation_ids[0])
        assert record.state is OperationState.INTERRUPTED
        assert not record.ownership_known and not record.writers_stopped
        assert record.blocked_reason == "writers_unconfirmed"
        with pytest.raises(HTTPException):
            get_server_write_admission().check("first")
        get_server_write_admission().check("other")
        if action == "cron":
            [legacy] = await env.cron.get_execution_history("scheduled-restart")
            assert legacy.status is ExecutionStatus.FAILED
            assert any("恢复验证" in message for message in legacy.messages)
            assert record.origin == "cron" and record.legacy_id == legacy.execution_id
        else:
            assert record.kind == f"server_{action}" and record.actor_id == 17
    finally:
        settle_now.set()
        daemon_release.set()
        tasks = [worker, *daemon_tasks]
        if restore_task is not None:
            tasks.append(restore_task)
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_cancellation_before_dispatch_does_not_leave_false_unknown_writer(daemon_runtime, monkeypatch):
    env = daemon_runtime
    original = env.journal.set_ownership_known

    async def cancelled_after_commit(operation_id, known):
        await original(operation_id, known)
        if not known:
            raise asyncio.CancelledError

    monkeypatch.setattr(env.journal, "set_ownership_known", cancelled_after_commit)
    with pytest.raises(asyncio.CancelledError):
        await env.manual("up")
    env.instance.up.assert_not_awaited()
    [record] = await env.journal.list()
    assert record.state is OperationState.INTERRUPTED
    assert record.writers_stopped and record.ownership_known and record.blocked_reason is None
    get_server_write_admission().check("first")


async def test_cron_known_stopped_cancellation_keeps_cancelled_projection(daemon_runtime):
    env = daemon_runtime
    entered = asyncio.Event()

    async def job(context):
        entered.set()
        await asyncio.Event().wait()

    worker = asyncio.create_task(env.cron._execute_cronjob_wrapper(
        "scheduled-restart", "restart_server", restart.ServerRestartParams(server_id="first"), job,
    ))
    await asyncio.wait_for(entered.wait(), 3)
    worker.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(worker, 3)
    [record] = await env.journal.list()
    [legacy] = await env.cron.get_execution_history("scheduled-restart")
    assert record.state is OperationState.CANCELLED and record.writers_stopped
    assert legacy.status is ExecutionStatus.CANCELLED
    assert not any("恢复验证" in message for message in legacy.messages)
    get_server_write_admission().check("first")


async def test_stopped_scheduled_restart_records_skip_without_starting_server(daemon_runtime):
    env = daemon_runtime
    env.instance.running.return_value = False
    await env.cron._execute_cronjob_wrapper(
        "scheduled-restart", "restart_server", restart.ServerRestartParams(server_id="first"),
        restart.restart_server_cronjob,
    )
    env.instance.restart.assert_not_awaited()
    env.instance.start.assert_not_awaited()
    [history] = await env.cron.get_execution_history("scheduled-restart")
    assert history.status is ExecutionStatus.SKIPPED
    assert history.ended_at is not None and history.duration_ms is not None
    assert any("未在运行中" in message for message in history.messages)
    [operation] = await env.journal.list()
    assert operation.state is OperationState.SKIPPED
    assert operation.ownership_known and operation.writers_stopped and not operation.data_changed
    assert operation.running_intent is None
    assert operation.legacy_id == history.execution_id
