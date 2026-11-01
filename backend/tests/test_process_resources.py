import asyncio
import sys
from pathlib import Path

import psutil
import pytest

from app.monitoring.cpu import read_process_counter


async def test_real_process_counter_measures_work_and_refuses_exited_process(monkeypatch):
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-u", "-c",
        "import ctypes\nctypes.CDLL(None).prctl(15, b'java', 0, 0, 0)\n"
        "print('ready', flush=True)\nwhile True: pass",
        stdout=asyncio.subprocess.PIPE,
    )
    read_text = Path.read_text

    def owned_cgroup(path, *args, **kwargs):
        if path == Path(f"/proc/{process.pid}/cgroup"):
            return "0::/docker/owned-test-container"
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", owned_cgroup)
    try:
        assert process.stdout is not None
        assert await asyncio.wait_for(process.stdout.readline(), 5) == b"ready\n"
        first = await asyncio.to_thread(read_process_counter, process.pid, "owned-test-container")
        await asyncio.sleep(0.2)
        second = await asyncio.to_thread(read_process_counter, process.pid, "owned-test-container")
        percentage = second.percent_since(first)
        assert percentage is not None and percentage > 0
        with pytest.raises(RuntimeError, match="归属"):
            await asyncio.to_thread(read_process_counter, process.pid, "another-container")
    finally:
        if process.returncode is None:
            process.terminate()
        await process.wait()
    with pytest.raises(psutil.NoSuchProcess):
        read_process_counter(process.pid, "owned-test-container")


def test_process_access_denied_is_not_reported_as_zero(monkeypatch):
    def denied(pid):
        raise psutil.AccessDenied(pid)

    monkeypatch.setattr("app.monitoring.cpu.psutil.Process", denied)
    with pytest.raises(psutil.AccessDenied):
        read_process_counter(101, "owned-test-container")
