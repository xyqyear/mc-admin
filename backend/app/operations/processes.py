"""Durable identity and cancellation for operation-owned child processes."""

import asyncio
import os
import signal
import sys
import time
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from weakref import WeakKeyDictionary

from .context import current_execution
from .finalization import finalize
from .journal_types import OperationRecord, ProcessIdentity
from .pidfd import open_pidfd, send_signal

_identities: WeakKeyDictionary[asyncio.subprocess.Process, ProcessIdentity] = WeakKeyDictionary()


def _identity(pid: int) -> ProcessIdentity | None:
    try:
        proc = Path("/proc") / str(pid)
        stat = (proc / "stat").read_text().rsplit(")", 1)[1].split()
        if stat[0] == "Z":
            return None
        root = (proc / "root").stat()
        return ProcessIdentity(
            pid=pid, pgid=int(stat[2]), start_ticks=int(stat[19]),
            boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            root_dev=root.st_dev, root_ino=root.st_ino,
        )
    except (FileNotFoundError, ProcessLookupError):
        return None


async def spawn_process(*args: str, **kwargs: Any) -> asyncio.subprocess.Process:
    execution = current_execution()
    read_fd, write_fd = os.pipe()
    process: asyncio.subprocess.Process | None = None

    async def launch() -> asyncio.subprocess.Process:
        nonlocal process
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(Path(__file__).with_name("process_gate.py")), str(read_fd),
            *args, pass_fds=(read_fd,), start_new_session=True, **kwargs,
        )
        identity = await asyncio.to_thread(_identity, process.pid)
        if identity is None:
            raise RuntimeError("操作进程在登记前退出")
        _identities[process] = identity
        if execution is not None:
            await execution.journal.register_process(execution.operation_id, identity)
        return process

    try:
        process = await finalize(launch())
        os.write(write_fd, b"1")
        return process
    except BaseException:
        if process is not None:
            await finalize(stop_process(process))
        raise
    finally:
        os.close(read_fd)
        os.close(write_fd)


async def _drain(stream: asyncio.StreamReader | None) -> None:
    if stream is not None:
        while await stream.read(65536):
            pass


def _group_pids(pgid: int) -> Iterator[int]:
    for path in Path("/proc").iterdir():
        if not path.name.isdecimal():
            continue
        try:
            stat = (path / "stat").read_text().rsplit(")", 1)[1].split()
        except (FileNotFoundError, ProcessLookupError):
            continue
        if stat[0] != "Z" and int(stat[2]) == pgid:
            yield int(path.name)


def _owned_handles(identity: ProcessIdentity) -> list[tuple[int, ProcessIdentity]]:
    if _identity(identity.pid) != identity:
        return []
    handles: list[tuple[int, ProcessIdentity]] = []
    deadline = time.monotonic() + 2.0
    try:
        # Freeze before enumeration so a late fork cannot outlive its parent.
        _freeze_process(identity, handles, deadline)
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("无法确认操作进程的完整归属")
            count = len(handles)
            known = {candidate.pid for _, candidate in handles}
            for pid in _group_pids(identity.pgid):
                if pid in known:
                    continue
                try:
                    candidate = _identity(pid)
                except PermissionError:
                    continue
                if candidate is None or (
                    candidate.pgid != identity.pgid or candidate.boot_id != identity.boot_id
                    or (candidate.root_dev, candidate.root_ino) != (identity.root_dev, identity.root_ino)
                    or candidate.start_ticks < identity.start_ticks
                ):
                    continue
                if _identity(identity.pid) != identity:
                    raise RuntimeError("操作进程归属在清理期间发生变化")
                _freeze_process(candidate, handles, deadline)
            if len(handles) == count:
                return handles
    except BaseException:
        _close_handles(handles)
        raise


def _freeze_process(
    identity: ProcessIdentity,
    handles: list[tuple[int, ProcessIdentity]],
    deadline: float,
) -> None:
    try:
        fd = open_pidfd(identity.pid)
    except ProcessLookupError:
        return
    try:
        matches = _identity(identity.pid) == identity
    except BaseException:
        os.close(fd)
        raise
    if not matches:
        os.close(fd)
        return
    handles.append((fd, identity))
    try:
        send_signal(fd, signal.SIGSTOP)
    except ProcessLookupError:
        return
    while _identity(identity.pid) == identity:
        try:
            state = (Path("/proc") / str(identity.pid) / "stat").read_text().rsplit(")", 1)[1].split()[0]
        except (FileNotFoundError, ProcessLookupError):
            return
        if state in {"T", "t", "Z"}:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("无法暂停操作进程以确认其子进程归属")
        time.sleep(0.001)


def _signal(handles: list[tuple[int, ProcessIdentity]], sig: signal.Signals) -> None:
    for fd, _ in handles:
        try:
            send_signal(fd, sig)
        except ProcessLookupError:
            pass


def _close_handles(handles: list[tuple[int, ProcessIdentity]]) -> None:
    try:
        _signal(handles, signal.SIGCONT)
    finally:
        for fd, _ in handles:
            os.close(fd)


@asynccontextmanager
async def _process_handles(
    identity: ProcessIdentity | None,
) -> AsyncGenerator[list[tuple[int, ProcessIdentity]]]:
    handles: list[tuple[int, ProcessIdentity]] = []

    async def collect() -> None:
        if identity is not None:
            handles.extend(await asyncio.to_thread(_owned_handles, identity))

    try:
        await finalize(collect())
        yield handles
    finally:
        _close_handles(handles)


async def stop_process(process: asyncio.subprocess.Process, *, grace: float = 2.0) -> None:
    identity = _identities.get(process)
    async with _process_handles(identity) as handles:
        _signal(handles, signal.SIGTERM)
        _signal(handles, signal.SIGCONT)
        try:
            await asyncio.wait_for(process.wait(), timeout=grace)
        except TimeoutError:
            _signal(handles, signal.SIGKILL)
        if identity is not None and not await asyncio.to_thread(_confirmed_exit, identity):
            _signal(handles, signal.SIGKILL)
        await asyncio.wait_for(
            asyncio.gather(_drain(process.stdout), _drain(process.stderr), process.wait()), timeout=grace,
        )
    execution = current_execution()
    if execution is not None and identity is not None:
        if await asyncio.to_thread(_confirmed_exit, identity):
            await execution.journal.process_stopped(execution.operation_id, identity.pid, identity.start_ticks)
        else:
            raise RuntimeError("操作所属的进程尚未全部结束")


def _confirmed_exit(identity: ProcessIdentity) -> bool:
    if Path("/proc/sys/kernel/random/boot_id").read_text().strip() != identity.boot_id:
        return True
    # Group membership is readable without inspecting unrelated process roots.
    return next(_group_pids(identity.pgid), None) is None


async def confirm_stopped(record: OperationRecord) -> bool:
    if not record.ownership_known:
        return False
    for identity in record.processes:
        try:
            if await asyncio.to_thread(_confirmed_exit, identity):
                continue
            async with _process_handles(identity) as handles:
                if not handles:
                    return False
                _signal(handles, signal.SIGTERM)
                _signal(handles, signal.SIGCONT)
                for _ in range(20):
                    if await asyncio.to_thread(_confirmed_exit, identity):
                        break
                    await asyncio.sleep(0.1)
                else:
                    _signal(handles, signal.SIGKILL)
                if not await asyncio.to_thread(_confirmed_exit, identity):
                    return False
        except (OSError, ValueError):
            return False
    return True
