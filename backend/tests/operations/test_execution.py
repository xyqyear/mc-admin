import asyncio
import sys
import threading
from pathlib import Path

import pytest

from app.background_tasks.manager import BackgroundTaskManager
from app.background_tasks.types import TaskProgress, TaskStatus, TaskType
from app.operations.context import OperationExecution, bind_execution
from app.operations.finalization import finalize
from app.operations.journal_types import (
    OperationSpec,
    OperationState,
    ResourceReference,
)
from app.utils.exec import exec_command_stream


async def test_process_cleanup_does_not_inspect_unrelated_process_roots(monkeypatch):
    import os

    from app.operations.processes import _group_pids

    unrelated = set(_group_pids(os.getpgrp()))
    stat = Path.stat

    def restricted_stat(path, *args, **kwargs):
        if path.parent.parent == Path("/proc") and path.name == "root" and int(path.parent.name) in unrelated:
            raise PermissionError("unrelated process root is not readable")
        return stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", restricted_stat)
    stream = exec_command_stream(sys.executable, "-c", "print('completed', flush=True)")
    assert [line async for line in stream] == ["completed\n"]


async def test_silent_operation_cancels_without_a_progress_yield_and_waits_for_cleanup():
    manager = BackgroundTaskManager()
    started, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def operation():
        started.set()
        try:
            await asyncio.Event().wait()
            yield TaskProgress(message="unreachable")
        finally:
            cleaning.set()
            await finalize(release.wait())

    submitted = manager.submit(TaskType.ARCHIVE_CREATE, "owned", operation())
    await started.wait()
    assert await manager.cancel(submitted.task_id)
    await cleaning.wait()
    assert not submitted.awaitable.done()
    assert submitted.task.status is TaskStatus.RUNNING
    assert manager.remove_task(submitted.task_id) is False
    assert await manager.cancel(submitted.task_id)
    release.set()
    result = await asyncio.wait_for(submitted.awaitable, 2)
    assert result.success is False
    assert submitted.task.status is TaskStatus.CANCELLED


async def test_cancelled_thread_write_is_still_owned_until_it_finishes():
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def write():
        started.set()
        release.wait(3)
        finished.set()

    task = asyncio.create_task(finalize(asyncio.to_thread(write)))
    await asyncio.to_thread(started.wait, 2)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    assert finished.is_set()


async def test_owned_subprocess_is_registered_before_running_and_reaped_before_finish(journal, tmp_path):
    record = await journal.accept(OperationSpec("world_restore", (ResourceReference("world", "owned", 1),)))
    await journal.start(record.operation_id)
    marker = tmp_path / "executed"
    script = "from pathlib import Path; import time; Path(__import__('sys').argv[1]).write_text('yes'); print('ready', flush=True); time.sleep(60)"
    with bind_execution(OperationExecution(journal, record.operation_id)):
        stream = exec_command_stream(sys.executable, "-c", script, str(marker))
        assert await anext(stream) == "ready\n"
        active = await journal.get(record.operation_id)
        assert active is not None and len(active.processes) == 1
        assert marker.read_text() == "yes"
        await asyncio.wait_for(stream.aclose(), 3)
        settled = await journal.get(record.operation_id)
        assert settled is not None and not settled.processes
        await journal.finish(record.operation_id, OperationState.CANCELLED, writers_stopped=True)


async def test_late_cancellation_preserves_the_already_committed_terminal_state(journal, monkeypatch):
    manager = BackgroundTaskManager(journal)
    committed, release = asyncio.Event(), asyncio.Event()
    finish = journal.finish

    async def commit_then_wait(*args, **kwargs):
        record = await finish(*args, **kwargs)
        committed.set()
        await release.wait()
        return record

    monkeypatch.setattr(journal, "finish", commit_then_wait)

    async def operation():
        yield TaskProgress(progress=100, result={"written": True})

    submitted = await manager.submit_durable(TaskType.ARCHIVE_CREATE, "owned", operation())
    await committed.wait()
    assert await manager.cancel(submitted.task_id)
    release.set()
    result = await asyncio.wait_for(submitted.awaitable, 2)
    record = await journal.get(submitted.task_id)
    assert record is not None and record.state is OperationState.SUCCEEDED
    assert result.success and submitted.task.status is TaskStatus.COMPLETED


async def test_durable_queued_cancellation_does_not_execute_the_generator(journal):
    manager = BackgroundTaskManager(journal)

    async def operation():
        pytest.fail("A cancelled queued operation executed")
        yield TaskProgress(progress=100)

    submitted = await manager.submit_durable(TaskType.ARCHIVE_CREATE, "owned", operation())
    assert await manager.cancel(submitted.task_id)
    await asyncio.wait_for(submitted.awaitable, 2)
    record = await journal.get(submitted.task_id)
    assert record is not None and record.state is OperationState.CANCELLED
    assert submitted.task.status is TaskStatus.CANCELLED


async def test_unconfirmed_writer_cannot_publish_a_successful_task(journal):
    from app.operations.context import current_execution

    manager = BackgroundTaskManager(journal)

    async def operation():
        execution = current_execution()
        assert execution is not None
        await journal.set_ownership_known(execution.operation_id, False)
        yield TaskProgress(progress=100)

    submitted = await manager.submit_durable(TaskType.ARCHIVE_CREATE, "owned", operation())
    result = await asyncio.wait_for(submitted.awaitable, 2)
    record = await journal.get(submitted.task_id)
    assert record is not None and record.state is OperationState.INTERRUPTED
    assert not result.success and submitted.task.status is TaskStatus.FAILED


async def test_registration_failure_never_opens_the_process_gate(journal, tmp_path, monkeypatch):
    record = await journal.accept(OperationSpec("world_restore", (ResourceReference("world", "owned", 1),)))
    await journal.start(record.operation_id)
    marker = tmp_path / "must-not-exist"

    async def reject(*args):
        raise RuntimeError("registration unavailable")

    monkeypatch.setattr(journal, "register_process", reject)
    with bind_execution(OperationExecution(journal, record.operation_id)):
        stream = exec_command_stream(sys.executable, "-c", "from pathlib import Path; import sys; Path(sys.argv[1]).touch()", str(marker))
        with pytest.raises(RuntimeError, match="registration unavailable"):
            await asyncio.wait_for(anext(stream), 3)
        await stream.aclose()
    assert not marker.exists()


async def test_stream_cleanup_escalates_without_competing_stderr_readers():
    script = "import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready',flush=True);\nwhile True: os.write(2,b'x'*8192)"
    stream = exec_command_stream(sys.executable, "-c", script)
    assert await asyncio.wait_for(anext(stream), 3) == "ready\n"
    await asyncio.wait_for(stream.aclose(), 5)
