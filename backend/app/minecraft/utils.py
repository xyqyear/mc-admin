import asyncio
import os
import shutil
from pathlib import Path

import psutil
from asyncer import asyncify
from psutil import NoSuchProcess, Process

process_obj_cache = dict[int, Process]()


async def async_rmtree(path: Path):
    await asyncio.to_thread(shutil.rmtree, path)


async def run_shell_command(command: str, catch_output: bool = True) -> str:
    """
    need to use catch_stderr=False for socat
    """
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE if catch_output else None,
        stderr=asyncio.subprocess.PIPE if catch_output else None,
    )

    stdout, stderr = await process.communicate()
    if stdout is None:  # type: ignore
        stdout = b""
    if stderr is None:  # type: ignore
        stderr = b""

    if process.returncode != 0:
        raise RuntimeError(f"Failed to run shell command: {command}\n{stderr.decode()}")
    return stdout.decode()


async def exec_command(
    command: str,
    *args: str,
    uid: int | None = None,
    gid: int | None = None,
    env: dict[str, str] = dict(),
) -> str:
    def demote():
        if uid is not None and gid is not None:
            os.setuid(uid)
            os.setgid(gid)

    process = await asyncio.create_subprocess_exec(
        command,
        *args,
        preexec_fn=demote,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()
    if stdout is None:  # type: ignore
        stdout = b""
    if stderr is None:  # type: ignore
        stderr = b""

    if process.returncode != 0:
        raise RuntimeError(f"Failed to exec command: {command}\n{stderr.decode()}")
    return stdout.decode()


@asyncify
def get_process_memory_usage(pid: int) -> int:
    """
    Get the memory usage of a process by its PID
    in bytes
    """
    try:
        process = process_obj_cache.get(pid, psutil.Process(pid))
        process_obj_cache[pid] = process
        return process.memory_info().rss
    except NoSuchProcess:
        return 0


@asyncify
def get_process_cpu_usage(pid: int) -> float:
    """
    Get the CPU usage of a process by its PID
    in percentage
    """
    try:
        process = process_obj_cache.get(pid, psutil.Process(pid))
        process_obj_cache[pid] = process
        return process.cpu_percent(1)
    except NoSuchProcess:
        return 0.0
