import asyncio
import sys

import anyio

from app.utils.exec import exec_command


async def test_anyio_cancellation_reaps_command_before_return(monkeypatch):
    real_spawn = asyncio.create_subprocess_exec
    started = asyncio.Event()
    processes: list[asyncio.subprocess.Process] = []

    async def spawn(*args, **kwargs):
        process = await real_spawn(*args, **kwargs)
        processes.append(process)
        started.set()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    with anyio.CancelScope() as scope:
        async with anyio.create_task_group() as group:

            async def cancel_after_spawn():
                await started.wait()
                scope.cancel()

            group.start_soon(cancel_after_spawn)
            await exec_command(sys.executable, "-c", "import time; time.sleep(60)")
    assert len(processes) == 1
    assert processes[0].returncode is not None
