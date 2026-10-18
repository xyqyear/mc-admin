import asyncio
import json
import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.background_tasks import TaskStatus
from app.operations import processes
from app.operations.journal_types import OperationState
from app.snapshots.models import ResticSnapshot
from app.snapshots.restic import ResticClient
from app.snapshots.scopes import PathsScope

from .support import complete

SUMMARY = {
    "message_type": "summary",
    "snapshot_id": "a" * 64,
    "backup_start": "2026-10-18T01:00:00Z",
    "backup_end": "2026-10-18T01:00:01Z",
    "total_files_processed": 1,
    "total_bytes_processed": 4,
}


@pytest.fixture
def controlled_backup(tmp_path, monkeypatch):
    original_spawn = processes.spawn_process

    def prepare(script):
        spawned = asyncio.get_running_loop().create_future()
        invocation = {}
        client = ResticClient(str(tmp_path / "repository"), binary_path=tmp_path / "restic")
        snapshot = ResticSnapshot(
            time=datetime.now(UTC), paths=[str(tmp_path)], hostname="test", username="test",
            id="a" * 64, short_id="a" * 8,
        )
        lookup = AsyncMock(return_value=snapshot)
        monkeypatch.setattr(client, "get_snapshot", lookup)

        async def spawn(*args, **kwargs):
            invocation.update(args=args, env=kwargs.get("env"))
            process = await original_spawn(
                sys.executable, "-u", "-c", script,
                stdin=asyncio.subprocess.PIPE, **kwargs,
            )
            spawned.set_result(process)
            return process

        monkeypatch.setattr(processes, "spawn_process", spawn)
        return SimpleNamespace(client=client, spawned=spawned, invocation=invocation, lookup=lookup)

    return prepare


async def test_status_is_live_but_summary_waits_for_successful_exit(controlled_backup, tmp_path):
    statuses = [
        {"percent_done": 0},
        {"total_bytes": 0, "percent_done": 0},
        {"total_bytes": 100, "percent_done": 0.25},
        {"total_bytes": "100", "percent_done": 0.5},
        {"total_bytes": 100, "percent_done": float("nan")},
        {"total_bytes": 100, "percent_done": True},
        {"total_bytes": 100, "percent_done": 2},
        {"total_bytes": 100, "percent_done": 1},
    ]
    lines = ["not json", "[]", *(
        json.dumps({"message_type": "status", **status}) for status in statuses
    ), json.dumps(SUMMARY)]
    script = (
        "import sys\n"
        "sys.stderr.write('x' * 1048576)\nsys.stderr.flush()\n"
        f"print({chr(10).join(lines)!r}, flush=True)\n"
        "sys.stdin.buffer.read(1)\n"
    )
    case = controlled_backup(script)
    observed = []
    ready = asyncio.Event()

    async def progress(percent):
        observed.append(percent)
        if percent == 1:
            ready.set()

    backup = asyncio.create_task(case.client.backup([tmp_path], on_progress=progress))
    try:
        await asyncio.wait_for(ready.wait(), 5)
        process = await case.spawned
        assert observed == [None, None, 0.25, None, None, None, None, 1]
        assert case.invocation["env"]["RESTIC_PROGRESS_FPS"] == "1"
        assert "RESTIC_PROGRESS_FPS" not in case.client.env
        assert case.invocation["args"][1:3] == ("backup", str(tmp_path))
        assert "--json" in case.invocation["args"]
        assert not backup.done() and process.returncode is None
        case.lookup.assert_not_awaited()
        process.stdin.write(b"1")
        await process.stdin.drain()
        result = await asyncio.wait_for(backup, 5)
        assert process.returncode == 0
        assert result.id == SUMMARY["snapshot_id"]
        assert result.summary is not None
        assert result.summary.total_bytes_processed == 4
        case.lookup.assert_awaited_once_with(SUMMARY["snapshot_id"])
    finally:
        if not backup.done():
            backup.cancel()
        await asyncio.gather(backup, return_exceptions=True)


async def test_summary_does_not_hide_unsuccessful_exit(controlled_backup, tmp_path):
    script = (
        "import sys\n"
        "sys.stderr.write('x' * 1048576 + ' failure tail')\nsys.stderr.flush()\n"
        f"print({json.dumps(SUMMARY)!r}, flush=True)\nsys.exit(3)\n"
    )
    case = controlled_backup(script)
    with pytest.raises(RuntimeError, match="restic backup failed \\(exit 3\\)") as failed:
        await case.client.backup([tmp_path], on_progress=AsyncMock())
    process = await case.spawned
    assert process.returncode == 3
    assert str(failed.value).endswith("failure tail")
    assert len(str(failed.value)) < 270000
    case.lookup.assert_not_awaited()


@pytest.mark.parametrize("failure", ["callback", "cancel"])
async def test_progress_failure_stops_owned_writer_before_return(
    controlled_backup, tmp_path, failure
):
    script = (
        "import sys\n"
        'print(\'{"message_type":"status","total_bytes":100,"percent_done":0.25}\', flush=True)\n'
        "sys.stdin.buffer.read(1)\n"
    )
    case = controlled_backup(script)
    ready = asyncio.Event()

    async def progress(_percent):
        ready.set()
        if failure == "callback":
            raise ValueError("progress callback failed")
        await asyncio.Event().wait()

    backup = asyncio.create_task(case.client.backup([tmp_path], on_progress=progress))
    try:
        await asyncio.wait_for(ready.wait(), 5)
        process = await case.spawned
        if failure == "cancel":
            backup.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(backup, 5)
        else:
            with pytest.raises(ValueError, match="progress callback failed"):
                await asyncio.wait_for(backup, 5)
        assert process.returncode is not None
        case.lookup.assert_not_awaited()
    finally:
        if not backup.done():
            backup.cancel()
        await asyncio.gather(backup, return_exceptions=True)


@pytest.mark.binary("restic")
@pytest.mark.parametrize("action", ["create", "restore", "rollback"])
async def test_manual_and_safety_progress_remains_running_until_backup_finishes(
    case, monkeypatch, action
):
    target = case.data / "settings.txt"
    target.write_text("source")
    scope = PathsScope(server_id="survival", paths=("settings.txt",))
    source = await case.snapshots.create_snapshot([target])
    target.write_text("before restore")
    parent = None
    if action == "rollback":
        parent = await case.commands.restore(scope, source.id, 1)
        await complete(case, parent)
        target.write_text("before rollback")
    before = target.read_bytes()
    original = case.snapshots.create_snapshot
    intermediate, full = asyncio.Event(), asyncio.Event()
    advance, release = asyncio.Event(), asyncio.Event()

    async def gated(*args, on_progress=None, **kwargs):
        assert on_progress is not None
        await on_progress(0.25)
        intermediate.set()
        await advance.wait()
        await on_progress(1)
        full.set()
        await release.wait()
        return await original(*args, on_progress=on_progress, **kwargs)

    monkeypatch.setattr(case.snapshots, "create_snapshot", gated)
    if action == "create":
        accepted = await case.commands.create(scope, 1)
    elif action == "restore":
        accepted = await case.commands.restore(scope, source.id, 1)
    else:
        assert parent is not None
        accepted = await case.commands.rollback(parent["restoration_id"], 1)
    future = case.tasks.get_future(accepted["task_id"])
    assert future is not None
    try:
        await asyncio.wait_for(intermediate.wait(), 5)
        task = case.tasks.get_task(accepted["task_id"])
        assert task.status is TaskStatus.RUNNING and task.progress == 25
        assert task.message == (
            "正在读取文件并创建快照" if action == "create" else "正在创建恢复前的安全快照"
        )
        assert target.read_bytes() == before
        advance.set()
        await asyncio.wait_for(full.wait(), 5)
        assert task.status is TaskStatus.RUNNING and task.progress == 100
        assert not future.done()
        if action != "create":
            row = await case.commands.store.get(accepted["restoration_id"])
            assert row.safety_snapshot_id is None
        assert target.read_bytes() == before
    finally:
        advance.set()
        release.set()
        await asyncio.wait_for(asyncio.shield(future), 30)
    result = await complete(case, accepted)
    if action == "create":
        assert result["snapshot"]["id"]
        assert target.read_bytes() == before
    else:
        assert result["safety_snapshot_id"]
        assert target.read_text() == ("source" if action == "restore" else "before restore")


@pytest.mark.binary("restic")
async def test_direct_backup_retains_awaited_result_without_task_progress(case, monkeypatch):
    original = case.snapshots.create_snapshot
    observed = []

    async def capture(*args, on_progress=None, **kwargs):
        observed.append(on_progress)
        return await original(*args, **kwargs)

    monkeypatch.setattr(case.snapshots, "create_snapshot", capture)
    result = await case.commands.backup(PathsScope(server_id="survival", paths=("server.properties",)))
    assert result.id and result.summary is not None
    assert result.summary.total_files_processed == 1
    assert observed == [None]


@pytest.mark.binary("restic")
async def test_cancel_live_backup_settles_after_owned_writer_and_lease_cleanup(
    case, controlled_backup, monkeypatch
):
    target = case.data / "settings.txt"
    target.write_text("retained content")
    script = (
        "import sys\n"
        'print(\'{"message_type":"status","total_bytes":100,"percent_done":0.25}\', flush=True)\n'
        "sys.stdin.buffer.read(1)\n"
    )
    controlled = controlled_backup(script)
    monkeypatch.setattr(case.snapshots, "_client", controlled.client)
    ready = asyncio.Event()
    update = case.tasks.update_progress

    def observe(task_id, progress):
        changed = update(task_id, progress)
        if progress.progress == 25:
            ready.set()
        return changed

    monkeypatch.setattr(case.tasks, "update_progress", observe)
    accepted = await case.commands.create(
        PathsScope(server_id="survival", paths=("settings.txt",)), 1
    )
    future = case.tasks.get_future(accepted["task_id"])
    assert future is not None
    try:
        await asyncio.wait_for(ready.wait(), 5)
        writer = await controlled.spawned
        assert writer.returncode is None
        record = await case.journal.get(accepted["task_id"])
        assert record.processes and record.state is OperationState.RUNNING
    finally:
        await case.tasks.cancel(accepted["task_id"])
        await asyncio.wait_for(asyncio.shield(future), 10)
    assert writer.returncode is not None
    assert case.tasks.get_task(accepted["task_id"]).status is TaskStatus.CANCELLED
    record = await case.journal.get(accepted["task_id"])
    assert record.state is OperationState.CANCELLED and record.writers_stopped
    assert not record.processes
    case.commands.require_deletable("survival")
    controlled.lookup.assert_not_awaited()
    assert target.read_text() == "retained content"
