import asyncio
import sys
from threading import Event

import psutil
import pytest

from app.utils import system


async def test_owned_process_sampling_and_exit():
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-u", "-c",
        "print('ready', flush=True)\nwhile True: pass",
        stdout=asyncio.subprocess.PIPE,
    )
    try:
        assert process.stdout is not None
        assert await asyncio.wait_for(process.stdout.readline(), 5) == b"ready\n"
        assert await system.get_process_cpu_usage(process.pid) > 0
    finally:
        if process.returncode is None:
            process.terminate()
        await process.wait()
    assert await system.get_process_cpu_usage(process.pid) == 0.0


async def test_access_denied_remains_an_error(monkeypatch):
    def denied(pid):
        raise psutil.AccessDenied(pid)

    monkeypatch.setattr(system.psutil, "Process", denied)
    with pytest.raises(psutil.AccessDenied):
        await system.get_process_cpu_usage(101)


async def test_sampling_runs_off_loop_and_keeps_multicore_percentage(monkeypatch):
    entered, release = Event(), Event()
    intervals = []

    class OwnedSample:
        def cpu_percent(self, interval):
            intervals.append(interval)
            entered.set()
            if not release.wait(5):
                raise TimeoutError("sample was not released")
            return 175.0

    monkeypatch.setattr(system.psutil, "Process", lambda pid: OwnedSample())
    sampling = asyncio.create_task(system.get_process_cpu_usage(102))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        assert not sampling.done()
    finally:
        release.set()
        result = await sampling
    assert result == 175.0
    assert intervals == [1]


async def test_reused_pid_is_sampled_from_current_process(monkeypatch):
    samples = iter([11, 22])

    class CurrentProcess:
        def __init__(self):
            self.percentage = next(samples)

        def cpu_percent(self, interval):
            assert interval == 1
            return self.percentage

    monkeypatch.setattr(system.psutil, "Process", lambda pid: CurrentProcess())
    assert await system.get_process_cpu_usage(103) == 11
    assert await system.get_process_cpu_usage(103) == 22
