import asyncio
import os
import sys

import pytest

from app.background_tasks.manager import BackgroundTaskManager
from app.background_tasks.types import TaskProgress, TaskStatus, TaskType
from app.utils.exec import exec_command, exec_command_stream


async def test_command_environment_does_not_inherit_parent_variables(monkeypatch):
    variable = "MC_ADMIN_TEST_EXEC_PARENT_ONLY"
    monkeypatch.setenv(variable, "parent-value")
    program = "import os; print(os.environ.get('MC_ADMIN_TEST_EXEC_PARENT_ONLY', 'absent'))"

    assert await exec_command(sys.executable, "-c", program) == "absent\n"
    assert await exec_command(sys.executable, "-c", program, env=None) == "absent\n"
    assert await exec_command(sys.executable, "-c", program, env={}) == "absent\n"
    assert await exec_command(
        sys.executable, "-c", program, env={variable: "child-value"}
    ) == "child-value\n"


async def test_cancellation_closes_generator_before_publishing_terminal_state():
    manager = BackgroundTaskManager()
    started = asyncio.Event()
    release = asyncio.Event()
    closed = False

    async def operation():
        nonlocal closed
        try:
            started.set()
            yield TaskProgress(progress=0, message="started")
            await release.wait()
            yield TaskProgress(progress=50, message="working")
        finally:
            await asyncio.sleep(0)
            closed = True

    submitted = manager.submit(
        task_type=TaskType.ARCHIVE_CREATE,
        name="cleanup ordering",
        task_generator=operation(),
    )
    await started.wait()
    assert await manager.cancel(submitted.task_id)
    release.set()
    result = await asyncio.wait_for(submitted.awaitable, timeout=2)
    assert not result.success
    assert closed
    assert submitted.task.status == TaskStatus.CANCELLED


async def test_closing_command_stream_reaps_its_child():
    stream = exec_command_stream(
        sys.executable,
        "-u",
        "-c",
        "import os,time; print(os.getpid(),flush=True); time.sleep(30)",
    )
    pid = int(await asyncio.wait_for(anext(stream), timeout=2))
    await asyncio.wait_for(stream.aclose(), timeout=3)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
