import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from httpx2 import ASGITransport, AsyncClient

from app.background_tasks import TaskProgress, TaskType, get_task_manager
from app.background_tasks.manager import BackgroundTaskManager
from app.db.metadata import Base
from app.main import api_app
from app.minecraft import DockerMCManager, MCInstance
from app.minecraft.docker.manager import ComposeManager
from app.operation_admission import get_server_write_admission
from app.operations.journal import OperationJournal
from app.operations.journal_types import OperationState, ResourceReference
from app.routers.servers.operations import server_maintenance
from app.servers.crud import create_server_record, mark_server_removed
from app.servers.lifecycle import CreateServerSpec, orchestrators
from app.servers.tasks import submit_creation, submit_lifecycle
from app.world.locks import LockHolder, ServerOperationKind, get_server_operation_lock
from tests.fixtures.test_utils import create_mc_server_compose_yaml
from tests.support.runtime import set_runtime_resource


@pytest.mark.parametrize("dismiss", ["single", "all"])
async def test_completed_result_survives_dismissal_and_restart(management, dismiss):
    env = management
    expected = {"snapshot": {"short_id": "retained-backup"}, "skipped_paths": []}

    async def complete():
        yield TaskProgress(progress=100, message="快照已完成", result=expected)

    accepted = await env.tasks.submit_durable(TaskType.SNAPSHOT_CREATE, "创建快照", complete())
    assert (await accepted.awaitable).success
    if dismiss == "single":
        assert env.tasks.remove_task(accepted.task_id)
    else:
        assert env.tasks.clear_completed() == 1
    assert env.tasks.get_all_tasks() == []
    detail = await env.tasks.get_task_detail(accepted.task_id)
    assert detail is not None and detail.status.value == "completed" and detail.result == expected
    assert env.tasks.get_all_tasks() == []
    restored = BackgroundTaskManager(env.journal)
    restored.restore_history(await env.journal.list(origin="task"))
    detail = await restored.get_task_detail(accepted.task_id)
    assert detail is not None and detail.status.value == "completed" and detail.result == expected
    assert await restored.get_task_detail("missing") is None


@pytest.fixture
async def management(isolated_runtime, monkeypatch):
    runtime = isolated_runtime
    async with runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    journal = OperationJournal(runtime.database.session_factory)
    runtime.journal = journal
    tasks = get_task_manager()
    tasks.journal = journal
    manager = DockerMCManager(runtime.settings.server_path)
    set_runtime_resource(monkeypatch, 'docker_mc_manager', manager)
    monkeypatch.setattr(orchestrators.get_log_monitor(), 'start_server', AsyncMock())
    monkeypatch.setattr(orchestrators.get_log_monitor(), 'stop_watching', AsyncMock())
    monkeypatch.setattr(orchestrators.get_dns_manager(), 'update', AsyncMock())
    monkeypatch.setattr(orchestrators, 'check_port_conflicts', AsyncMock(return_value=[]))
    monkeypatch.setattr(ComposeManager, 'created', AsyncMock(return_value=False))
    instance = manager.get_instance('managed')
    await instance.create(create_mc_server_compose_yaml('managed', 35401, 35402))
    async with runtime.database.session_factory() as session:
        record = await create_server_record(session, 'managed')
        generation = record.id
    yield SimpleNamespace(runtime=runtime, journal=journal, tasks=tasks, instance=instance, generation=generation)
    await tasks.shutdown()


async def completed(env, accepted):
    future = env.tasks.get_future(accepted.task_id)
    assert future is not None
    return await asyncio.wait_for(asyncio.shield(future), 5)


async def test_acceptance_exposes_reason_and_refuses_conflicts_until_terminal(management, monkeypatch):
    env = management
    entered, release = asyncio.Event(), asyncio.Event()

    async def up(_self):
        entered.set()
        await release.wait()

    monkeypatch.setattr(MCInstance, 'up', up)
    accepted = await asyncio.wait_for(submit_lifecycle('managed', 'up', 1), 2)
    try:
        await asyncio.wait_for(entered.wait(), 2)
        status = await server_maintenance('managed', Mock())
        assert status['active'] and status['task_id'] == accepted.task_id
        assert '镜像' in status['description']
        with pytest.raises(HTTPException) as conflict:
            await submit_lifecycle('managed', 'down', 1)
        assert conflict.value.status_code == 423
        assert conflict.value.detail == {
            'code': 'task_conflict', 'task_id': accepted.task_id,
            'message': '已有相同或冲突的任务正在执行，请等待完成',
        }
        assert not env.tasks.get_task(accepted.task_id).cancellable
    finally:
        release.set()
    assert (await completed(env, accepted)).success
    record = await env.journal.get(accepted.task_id)
    assert record and record.state is OperationState.SUCCEEDED and record.origin == 'task'
    assert not (await server_maintenance('managed', Mock()))['active']


async def test_queued_task_cannot_target_a_same_name_replacement(management, monkeypatch):
    env = management
    entered, release = asyncio.Event(), asyncio.Event()
    original = env.journal.start

    async def delayed_start(operation_id):
        entered.set()
        await release.wait()
        return await original(operation_id)

    monkeypatch.setattr(env.journal, 'start', delayed_start)
    stop = AsyncMock()
    monkeypatch.setattr(ComposeManager, 'stop', stop)
    accepted = await submit_lifecycle('managed', 'stop', 1)
    await asyncio.wait_for(entered.wait(), 2)
    async with env.runtime.database.session_factory() as session:
        await mark_server_removed(session, 'managed', datetime.now(UTC))
        replacement = await create_server_record(session, 'managed')
        assert replacement.id != env.generation
    release.set()
    assert not (await completed(env, accepted)).success
    stop.assert_not_awaited()
    assert '已变更' in env.tasks.get_task(accepted.task_id).error


async def test_removal_does_not_wait_for_itself(management):
    env = management
    accepted = await submit_lifecycle('managed', 'remove', 1)
    result = await completed(env, accepted)
    assert result.success and result.data
    assert accepted.task_id not in result.data['cancelled_background_task_ids']
    assert not env.instance.get_project_path().exists()
    assert not get_server_write_admission().is_frozen('managed')


@pytest.mark.parametrize('kind', [ServerOperationKind.RESTORE, ServerOperationKind.BACKUP])
async def test_removal_during_snapshot_maintenance_preserves_server_and_accepts_no_task(management, kind):
    env = management
    marker = env.instance.get_project_path() / 'data' / 'world-marker'
    marker.write_bytes(b'world must survive maintenance')
    holder = LockHolder(kind, datetime.now(UTC), 1, '正在维护世界')
    lock = get_server_operation_lock()
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url='http://test') as client:
        async with lock.acquire('managed', holder):
            response = await client.post(
                '/servers/managed/operations',
                json={'action': 'remove'},
                headers={'Authorization': f'Bearer {env.runtime.settings.master_token}'},
            )
            assert response.status_code == 423, response.text
            assert '维护' in response.json()['detail']
            assert not env.tasks.get_tasks_by_server_id('managed')
            assert lock.get_holder('managed') == holder
            assert marker.read_bytes() == b'world must survive maintenance'
        response = await client.post(
            '/servers/managed/operations',
            json={'action': 'remove'},
            headers={'Authorization': f'Bearer {env.runtime.settings.master_token}'},
        )
        assert response.status_code == 202, response.text
    result = await completed(env, SimpleNamespace(task_id=response.json()['task_id']))
    assert result.success, result.error
    assert not env.instance.get_project_path().exists()


async def test_removal_waits_for_cancelled_prune_writer_before_deleting_files(management):
    env = management
    entered, cancelling, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    marker = env.instance.get_data_path() / 'world-marker'
    marker.write_bytes(b'writer still owns this world')

    async def prune():
        holder = LockHolder(ServerOperationKind.PRUNE, datetime.now(UTC), 1, '正在清理区块')
        async with get_server_operation_lock().acquire('managed', holder):
            entered.set()
            try:
                await asyncio.Event().wait()
                yield TaskProgress(progress=100)
            finally:
                cancelling.set()
                await release.wait()

    writer = await env.tasks.submit_durable(TaskType.CHUNK_PRUNE_APPLY, '清理区块', prune(), server_id='managed')
    try:
        await asyncio.wait_for(entered.wait(), 2)
        accepted = await submit_lifecycle('managed', 'remove', 1)
        await asyncio.wait_for(cancelling.wait(), 2)
        assert marker.read_bytes() == b'writer still owns this world'
        assert get_server_write_admission().is_frozen('managed')
        with pytest.raises(HTTPException) as conflict:
            await submit_lifecycle('managed', 'start', 1)
        assert conflict.value.status_code == 423
        status = await server_maintenance('managed', Mock())
        assert status['task_id'] == accepted.task_id and status['kind'] == 'server_remove'
    finally:
        release.set()
    assert not (await writer.awaitable).success
    result = await completed(env, accepted)
    assert result.success, result.error
    assert result.data['cancelled_background_task_ids'] == [writer.task_id]
    assert not env.instance.get_project_path().exists()
    record = await env.journal.get(writer.task_id)
    assert record and record.state is OperationState.CANCELLED and record.writers_stopped


async def test_creation_binds_committed_generation_and_preserves_prepared_yaml(management, monkeypatch):
    env = management
    yaml = create_mc_server_compose_yaml('new', 35411, 35412).replace('EULA:', 'SERVER_PORT: "25565"\n      EULA:')
    spec = CreateServerSpec(yaml_content=yaml)
    accepted = await submit_creation('new', spec, 1)
    spec.yaml_content = 'invalid after acceptance'
    result = await completed(env, accepted)
    assert result.success, result.error
    record = await env.journal.get(accepted.task_id)
    assert record and record.resources[0].server_id == 'new'
    assert record.resources[0].generation and record.resources[0].generation != env.generation
    content = (env.runtime.settings.server_path / 'new' / 'docker-compose.yml').read_text()
    assert 'invalid after acceptance' not in content


@pytest.mark.parametrize('action', ['stop', 'down'])
async def test_recovery_stop_does_not_clear_protection(management, monkeypatch, action):
    env = management
    mutation = AsyncMock()
    monkeypatch.setattr(ComposeManager, action, mutation)
    admission = get_server_write_admission()
    admission.block('managed', '请检查中断操作')
    accepted = await submit_lifecycle('managed', action, 1)
    assert (await completed(env, accepted)).success
    mutation.assert_awaited_once()
    assert admission.recovery_reason('managed') == '请检查中断操作'
    admission.unblock('managed')


async def test_atomic_reservation_covers_journal_acceptance_and_releases_on_failure(management, monkeypatch):
    env = management
    entered, release = asyncio.Event(), asyncio.Event()
    original = env.journal.accept

    async def delayed(spec, **kwargs):
        entered.set()
        await release.wait()
        return await original(spec, **kwargs)

    monkeypatch.setattr(env.journal, 'accept', delayed)
    submission = asyncio.create_task(submit_lifecycle('managed', 'stop', 1))
    await asyncio.wait_for(entered.wait(), 2)
    with pytest.raises(HTTPException) as conflict:
        await submit_lifecycle('managed', 'down', 1)
    assert conflict.value.status_code == 423
    submission.cancel()
    with pytest.raises(asyncio.CancelledError):
        await submission
    release.set()
    monkeypatch.setattr(ComposeManager, 'stop', AsyncMock())
    accepted = await submit_lifecycle('managed', 'stop', 1)
    assert (await completed(env, accepted)).success
    record = await env.journal.get(accepted.task_id)
    assert record and record.resources == (ResourceReference('server', 'managed', env.generation),)


async def test_sync_revalidates_remaining_generations_after_multiple_deactivations(management):
    from app.servers.api_models import SyncRequest
    from app.servers.synchronization import submit_sync

    env = management
    async with env.runtime.database.session_factory() as session:
        await create_server_record(session, 'missing-one')
        await create_server_record(session, 'missing-two')
    accepted = await submit_sync(SyncRequest(force=True), 1)
    result = await completed(env, accepted)
    assert result.success and result.data, result.error
    assert not result.data['errors']
    assert {entry['server_id'] for entry in result.data['removed']} == {'missing-one', 'missing-two'}
    record = await env.journal.get(accepted.task_id)
    assert record and {resource.server_id for resource in record.resources if resource.server_id} == {'managed', 'missing-one', 'missing-two'}
    assert await env.instance.exists()


async def test_shutdown_during_creation_waits_for_rollback(management, monkeypatch):
    env = management
    entered = asyncio.Event()

    async def start_monitor(_server_id):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(orchestrators.get_log_monitor(), 'start_server', start_monitor)
    yaml = create_mc_server_compose_yaml('interrupted', 35421, 35422).replace('EULA:', 'SERVER_PORT: "25565"\n      EULA:')
    accepted = await submit_creation('interrupted', CreateServerSpec(yaml_content=yaml), 1)
    await asyncio.wait_for(entered.wait(), 2)
    await asyncio.wait_for(env.tasks.shutdown(), 5)
    result = await completed(env, accepted)
    assert not result.success
    assert not (env.runtime.settings.server_path / 'interrupted').exists()
    record = await env.journal.get(accepted.task_id)
    assert record and record.state is OperationState.CANCELLED and record.writers_stopped
