import asyncio
from types import SimpleNamespace

import httpx2
import pytest
from fastapi import HTTPException

from app.cron import crud
from app.cron.jobs import backup
from app.cron.manager import CronManager
from app.cron.models import ExecutionStatus
from app.cron.types import ExecutionContext
from app.db.metadata import Base
from app.dynamic_config.configs.snapshots import SnapshotsConfig
from app.minecraft import get_docker_mc_manager
from app.operations.journal import OperationJournal
from app.operations.journal_types import OperationState
from app.servers.models import Server
from app.snapshots import ResticClient, SnapshotService
from app.snapshots.commands import get_snapshot_commands
from app.utils.exec import exec_command
from tests.support.runtime import replace_runtime_resource

KUMA_URL = "https://monitor.invalid/api/push/private-url-secret"
PRIVATE_ERROR = "adapter credential=private-error-secret"


@pytest.fixture
async def owned_backup(isolated_runtime, tmp_path):
    runtime = isolated_runtime
    replace_runtime_resource(runtime, "dynamic_configuration", SimpleNamespace(snapshots=SnapshotsConfig()))
    async with runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with runtime.database.session_factory() as session:
        session.add(Server(server_id="survival"))
        await session.commit()
        await crud.create_cronjob(
            session, cronjob_id="safety-backup", identifier="backup", name="备份安全测试",
            cron="0 0 * * *", params_json='{"enable_forget": true, "keep_last": 1}',
        )
    project = runtime.settings.server_path / "survival"
    (project / "data").mkdir(parents=True)
    (project / "compose.yaml").write_text(
        "services:\n"
        "  mc:\n"
        "    container_name: mc-survival\n"
        "    image: itzg/minecraft-server:java21\n"
        "    environment: {VERSION: '1.21.1'}\n"
        "    ports: ['25565:25565', '25575:25575']\n"
    )
    data = project / "data" / "settings.txt"
    data.write_bytes(b"retained cron snapshot data\x00\xff")
    client = ResticClient(str(tmp_path / "repository"), password="cron-safety-test")
    await exec_command(str(client.binary_path), "init", env=client.env)
    service = SnapshotService(client, get_docker_mc_manager())
    replace_runtime_resource(runtime, "snapshot_service", service)
    journal = OperationJournal(runtime.database.session_factory)
    runtime.journal = journal
    manager = CronManager()
    try:
        yield runtime, manager, service, journal, data
    finally:
        await manager.shutdown()


def intercept_kuma(monkeypatch, outcome: str, requests: list[httpx2.Request]) -> None:
    original_client = httpx2.AsyncClient

    def receive(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if outcome == "http":
            raise httpx2.HTTPError(PRIVATE_ERROR)
        if outcome == "ordinary":
            raise RuntimeError(PRIVATE_ERROR)
        if outcome == "cancelled":
            raise asyncio.CancelledError()
        return httpx2.Response(200)

    monkeypatch.setattr(backup.httpx2, "AsyncClient", lambda **kwargs: original_client(transport=httpx2.MockTransport(receive), **kwargs))


@pytest.mark.binary("restic")
@pytest.mark.parametrize(
    "forget_outcome,status,operation_state,kuma_status",
    [
        ("busy", ExecutionStatus.SKIPPED, OperationState.SKIPPED, "up"),
        ("http", ExecutionStatus.FAILED, OperationState.FAILED, "down"),
        ("ordinary", ExecutionStatus.COMPLETED, OperationState.SUCCEEDED, "up"),
    ],
)
@pytest.mark.parametrize("notification_outcome", ["ok", "http", "ordinary"])
async def test_real_snapshot_retains_forget_outcome_when_notification_fails(
    owned_backup, monkeypatch, caplog, forget_outcome, status, operation_state, kuma_status, notification_outcome,
):
    runtime, manager, service, journal, data = owned_backup
    error = (
        HTTPException(423 if forget_outcome == "busy" else 409, detail=PRIVATE_ERROR)
        if forget_outcome != "ordinary"
        else RuntimeError(PRIVATE_ERROR)
    )
    requests: list[httpx2.Request] = []
    intercept_kuma(monkeypatch, notification_outcome, requests)

    async def fail_retention(**_kwargs):
        assert len(await service.list_snapshots()) == 1
        raise error

    monkeypatch.setattr(service, "forget", fail_retention)
    execution_ids = []
    propagated = []

    async def run_backup(context: ExecutionContext) -> None:
        execution_ids.append(context.execution_id)
        try:
            await backup.backup_cronjob(context)
        except HTTPException as raised:
            propagated.append(raised)
            raise

    await manager._execute_cronjob_wrapper(
        "safety-backup", "backup", backup.BackupJobParams(keep_last=1, uptimekuma_url=KUMA_URL), run_backup,
    )
    history = await manager.get_execution_history("safety-backup")
    assert len(history) == 1 and execution_ids == [history[0].execution_id]
    assert history[0].status == status
    assert history[0].ended_at is not None and history[0].duration_ms is not None and history[0].duration_ms >= 0
    assert propagated == ([error] if forget_outcome == "http" else [])
    if propagated:
        assert propagated[0] is error and type(propagated[0]) is HTTPException
    async with runtime.database.session_factory() as session:
        job = await crud.get_cronjob(session, "safety-backup")
        assert job is not None and job.execution_count == 1
    records = await journal.list()
    assert len(records) == 1 and records[0].state == operation_state
    assert records[0].writers_stopped and not records[0].processes
    saved = await service.list_snapshots()
    assert len(saved) == 1 and saved[0].paths == [str(runtime.settings.server_path)]
    assert data.read_bytes() == b"retained cron snapshot data\x00\xff"
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url).split("?")[0] == KUMA_URL
    assert request.url.params["status"] == kuma_status
    assert int(request.url.params["ping"]) >= 0
    message = request.url.params["msg"]
    if forget_outcome == "busy":
        assert message.startswith("skipped: 快照已创建")
    elif forget_outcome == "ordinary":
        assert message == "OK"
        assert any("警告: 清理旧快照时出错" in entry for entry in history[0].messages)
    else:
        assert message.startswith("备份任务失败:")
    assert "private-error-secret" not in message
    public_output = "\n".join(history[0].messages) + caplog.text
    assert "private-error-secret" not in public_output and KUMA_URL not in public_output


@pytest.mark.binary("restic")
@pytest.mark.parametrize("phase", ["backup", "forget", "notification"])
async def test_cancelled_backup_propagates_and_commits_same_execution(owned_backup, monkeypatch, caplog, phase):
    runtime, manager, service, journal, data = owned_backup
    requests: list[httpx2.Request] = []
    intercept_kuma(monkeypatch, "cancelled" if phase == "notification" else "ok", requests)

    async def cancel_boundary(*_args, **_kwargs):
        raise asyncio.CancelledError()

    if phase == "backup":
        commands = get_snapshot_commands()
        assert commands is not None
        monkeypatch.setattr(commands, "backup", cancel_boundary)
    elif phase == "forget":
        monkeypatch.setattr(service, "forget", cancel_boundary)
    execution_ids = []

    async def run_backup(context: ExecutionContext) -> None:
        execution_ids.append(context.execution_id)
        await backup.backup_cronjob(context)

    params = backup.BackupJobParams(enable_forget=phase == "forget", keep_last=1, uptimekuma_url=KUMA_URL)
    with pytest.raises(asyncio.CancelledError):
        await manager._execute_cronjob_wrapper("safety-backup", "backup", params, run_backup)
    history = await manager.get_execution_history("safety-backup")
    assert len(history) == 1 and execution_ids == [history[0].execution_id]
    assert history[0].status == ExecutionStatus.CANCELLED and history[0].ended_at is not None
    async with runtime.database.session_factory() as session:
        job = await crud.get_cronjob(session, "safety-backup")
        assert job is not None and job.execution_count == 1
    records = await journal.list()
    assert len(records) == 1 and records[0].state == OperationState.CANCELLED
    assert records[0].writers_stopped and not records[0].processes
    assert len(await service.list_snapshots()) == (0 if phase == "backup" else 1)
    assert data.read_bytes() == b"retained cron snapshot data\x00\xff"
    assert len(requests) == (1 if phase == "notification" else 0)
    assert KUMA_URL not in "\n".join(history[0].messages) + caplog.text
