"""Per-process CPU and memory queries via psutil, off-loaded to threads."""

import asyncio

import psutil
from psutil import NoSuchProcess, Process

from ..runtime_resources import current_runtime


# Reusing the psutil Process keeps cpu_percent's interval baseline warm across calls.
def get_process_cache() -> dict[int, Process]:
    return current_runtime().resource('process_cache')


async def get_process_memory_usage(pid: int) -> int:
    """RSS in bytes; 0 if the process is gone."""
    return await asyncio.to_thread(_memory_usage_sync, pid)


def _memory_usage_sync(pid: int) -> int:
    try:
        process = get_process_cache().get(pid, psutil.Process(pid))
        get_process_cache()[pid] = process
        return process.memory_info().rss
    except NoSuchProcess:
        return 0


async def get_process_cpu_usage(pid: int) -> float:
    """CPU usage as 0.0-100.0; blocks the worker thread 1s to sample. 0.0 if gone."""
    return await asyncio.to_thread(_cpu_usage_sync, pid)


def _cpu_usage_sync(pid: int) -> float:
    try:
        process = get_process_cache().get(pid, psutil.Process(pid))
        get_process_cache()[pid] = process
        return process.cpu_percent(1)
    except NoSuchProcess:
        return 0.0
