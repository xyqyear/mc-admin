import asyncio
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from app.operations import processes


async def test_reaped_process_group_is_confirmed_without_host_scan(monkeypatch):
    process = await processes.spawn_process(sys.executable, "-c", "pass")
    identity = processes._identities[process]
    await process.wait()

    def unexpected_scan(_pgid):
        raise AssertionError("An absent group does not require a host scan")

    monkeypatch.setattr(processes, "_group_pids", unexpected_scan)
    assert processes._confirmed_exit(identity)
    await processes.stop_process(process)


@pytest.mark.parametrize("error", [None, PermissionError(), OSError("unknown")])
@pytest.mark.parametrize("members", [[], [12345]])
def test_present_or_uncertain_group_requires_membership_confirmation(monkeypatch, error, members):
    identity = processes._identity(os.getpid())
    assert identity is not None
    identity = replace(identity, pgid=12345)

    def probe(pgid, sig):
        assert pgid == 12345 and sig == 0
        if error is not None:
            raise error

    monkeypatch.setattr(processes.os, "killpg", probe)
    monkeypatch.setattr(processes, "_group_pids", lambda _pgid: iter(members))
    assert processes._confirmed_exit(identity) is (not members)


def test_previous_boot_does_not_probe_a_reused_group(monkeypatch):
    identity = processes._identity(os.getpid())
    assert identity is not None

    def unexpected_probe(*args):
        raise AssertionError("An old boot cannot own current processes")

    monkeypatch.setattr(processes.os, "killpg", unexpected_probe)
    assert processes._confirmed_exit(replace(identity, boot_id="previous-boot"))


@pytest.mark.parametrize("namespace_stat", ["1 (foreign)", "invalid", None])
def test_unconfirmed_pid_namespace_keeps_membership_scan(monkeypatch, namespace_stat):
    identity = processes._identity(os.getpid())
    assert identity is not None
    read_text = Path.read_text

    def read(path, *args, **kwargs):
        if path == Path("/proc/self/stat"):
            if namespace_stat is None:
                raise PermissionError("namespace unavailable")
            return namespace_stat
        return read_text(path, *args, **kwargs)

    def unexpected_probe(*args):
        raise AssertionError("Signal 0 requires matching namespace evidence")

    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(processes.os, "killpg", unexpected_probe)
    monkeypatch.setattr(processes, "_group_pids", lambda _pgid: iter([identity.pid]))
    assert not processes._confirmed_exit(identity)


async def test_zombie_only_group_is_confirmed_by_fallback_scan(tmp_path):
    release = tmp_path / "exit"
    # Keep the zombie unreaped so signal 0 still observes its process group.
    process = await asyncio.to_thread(subprocess.Popen, [
        sys.executable, "-c", ("import pathlib, time\n"
        f"while not pathlib.Path({str(release)!r}).exists(): time.sleep(0.001)\n"),
    ], start_new_session=True)
    try:
        identity = processes._identity(process.pid)
        assert identity is not None
        release.touch()
        async with asyncio.timeout(5):
            while (Path(f"/proc/{process.pid}/stat").read_text().rsplit(")", 1)[1].split()[0]) != "Z":
                await asyncio.sleep(0.01)
        os.killpg(process.pid, 0)
        assert processes._confirmed_exit(identity)
    finally:
        release.touch()
        process.kill()
        await asyncio.to_thread(process.wait, 5)


async def test_parent_exit_does_not_confirm_a_live_child(tmp_path):
    release = tmp_path / "parent-exit"
    process = await processes.spawn_process(
        sys.executable, "-c",
        "import os, pathlib, time\n"
        "if os.fork() == 0:\n"
        " print(os.getpid(), flush=True)\n"
        " time.sleep(30)\n"
        "else:\n"
        f" while not pathlib.Path({str(release)!r}).exists(): time.sleep(0.001)\n"
        " os._exit(0)\n",
        stdout=asyncio.subprocess.PIPE,
    )
    identity = processes._identities[process]
    child_fd = None
    try:
        assert process.stdout is not None
        child_pid = int(await asyncio.wait_for(process.stdout.readline(), 5))
        child_fd = processes.open_pidfd(child_pid)
        release.touch()
        async with asyncio.timeout(5):
            while process.returncode is None:
                await asyncio.sleep(0.01)
        assert not processes._confirmed_exit(identity)
    finally:
        if child_fd is not None:
            processes.send_signal(child_fd, signal.SIGKILL)
            os.close(child_fd)
        release.touch()
        await asyncio.wait_for(process.communicate(), 5)
    assert processes._confirmed_exit(identity)


async def test_worker_ignoring_term_is_killed_and_reaped():
    process = await processes.spawn_process(
        sys.executable, "-c",
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "print('ready', flush=True)\n"
        "time.sleep(30)\n",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    identity = processes._identities[process]
    try:
        assert process.stdout is not None
        assert await asyncio.wait_for(process.stdout.readline(), 5) == b"ready\n"
        await asyncio.wait_for(processes.stop_process(process, grace=0.05), 5)
        assert process.returncode == -signal.SIGKILL
        assert processes._confirmed_exit(identity)
        assert process.stdout.at_eof()
        assert process.stderr is not None and process.stderr.at_eof()
        await processes.stop_process(process)
    finally:
        if process.returncode is None:
            await processes.stop_process(process, grace=0.05)


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
