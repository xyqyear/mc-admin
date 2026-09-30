import asyncio
import os
import signal
import sys
import threading
import time
from pathlib import Path

import pytest

from app.operations import processes


@pytest.mark.parametrize("during_discovery", [False, True])
async def test_cancellation_stops_descendants_and_closes_inherited_pipes(
    tmp_path, monkeypatch, during_discovery
):
    gate = tmp_path / "fork"
    child_pid = tmp_path / "child.pid"
    ready = tmp_path / "ready"
    script = tmp_path / "worker.py"
    script.write_text(
        "import os, pathlib, time\n"
        f"gate = pathlib.Path({str(gate)!r})\n"
        f"pathlib.Path({str(ready)!r}).touch()\n"
        "while not gate.exists(): time.sleep(0.001)\n"
        "if os.fork() == 0:\n"
        f"    pathlib.Path({str(child_pid)!r}).write_text(str(os.getpid()))\n"
        "    time.sleep(30)\n"
        "else:\n"
        "    time.sleep(30)\n"
    )
    process = await processes.spawn_process(
        sys.executable, str(script),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    group_pids = processes._group_pids
    try:
        async with asyncio.timeout(5):
            while not ready.exists():
                await asyncio.sleep(0.01)
        if during_discovery:
            released = False

            def discover(pgid):
                nonlocal released
                members = list(group_pids(pgid))
                yield from members
                if not released:
                    released = True
                    gate.touch()
                    deadline = time.monotonic() + 0.1
                    while not child_pid.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)

            monkeypatch.setattr(processes, "_group_pids", discover)
        else:
            gate.touch()
            async with asyncio.timeout(5):
                while not child_pid.exists():
                    await asyncio.sleep(0.01)
        await processes.stop_process(process, grace=0.3)
        await processes.stop_process(process, grace=0.3)
        assert process.returncode is not None
        assert list(group_pids(process.pid)) == []
        assert process.stdout is not None and process.stdout.at_eof()
        assert process.stderr is not None and process.stderr.at_eof()
    finally:
        # These PIDs are descendants of the still-owned test process group.
        for pid in group_pids(process.pid):
            try:
                fd = processes.open_pidfd(pid)
            except ProcessLookupError:
                continue
            try:
                processes.send_signal(fd, signal.SIGKILL)
            finally:
                os.close(fd)
        await process.communicate()


async def test_failed_discovery_resumes_worker_without_guessing_ownership(
    tmp_path, monkeypatch
):
    gate = tmp_path / "continue"
    script = (
        "import pathlib, time\n"
        "print('ready', flush=True)\n"
        f"while not pathlib.Path({str(gate)!r}).exists(): time.sleep(0.001)\n"
        "print('resumed', flush=True)\n"
        "time.sleep(30)\n"
    )
    process = await processes.spawn_process(
        sys.executable, "-c", script,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        assert process.stdout is not None
        assert await asyncio.wait_for(process.stdout.readline(), 5) == b"ready\n"

        def unavailable(_pgid):
            raise PermissionError("test discovery unavailable")

        with monkeypatch.context() as patch:
            patch.setattr(processes, "_group_pids", unavailable)
            with pytest.raises(PermissionError):
                await processes.stop_process(process)
        assert process.returncode is None
        gate.touch()
        assert await asyncio.wait_for(process.stdout.readline(), 5) == b"resumed\n"
    finally:
        await processes.stop_process(process)


async def test_cancelled_discovery_waits_for_thread_and_resumes_captured_worker(
    monkeypatch,
):
    process = await processes.spawn_process(
        sys.executable, "-c", "import time; time.sleep(30)",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    captured, release = threading.Event(), threading.Event()
    owned_handles = processes._owned_handles

    def paused_discovery(identity):
        handles = owned_handles(identity)
        captured.set()
        release.wait(5)
        return handles

    stopping = None
    try:
        with monkeypatch.context() as patch:
            patch.setattr(processes, "_owned_handles", paused_discovery)
            stopping = asyncio.create_task(processes.stop_process(process))
            assert await asyncio.to_thread(captured.wait, 5)
            stopping.cancel()
            await asyncio.sleep(0)
            assert not stopping.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await stopping
        assert process.returncode is None
        async with asyncio.timeout(5):
            while (Path("/proc") / str(process.pid) / "stat").read_text().rsplit(")", 1)[1].split()[0] in {"T", "t"}:
                await asyncio.sleep(0.001)
    finally:
        release.set()
        if stopping is not None:
            await asyncio.gather(stopping, return_exceptions=True)
        await processes.stop_process(process)
