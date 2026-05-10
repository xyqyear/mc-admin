"""Per-process CPU and memory queries via psutil, off-loaded to threads."""

import asyncio

import psutil
from psutil import NoSuchProcess, Process

# Reusing the psutil Process keeps cpu_percent's interval baseline warm across calls.
process_obj_cache = dict[int, Process]()


async def get_process_memory_usage(pid: int) -> int:
    """RSS in bytes; 0 if the process is gone."""
    return await asyncio.to_thread(_memory_usage_sync, pid)


def _memory_usage_sync(pid: int) -> int:
    try:
        process = process_obj_cache.get(pid, psutil.Process(pid))
        process_obj_cache[pid] = process
        return process.memory_info().rss
    except NoSuchProcess:
        return 0


async def get_process_cpu_usage(pid: int) -> float:
    """CPU usage as 0.0-100.0; blocks the worker thread 1s to sample. 0.0 if gone."""
    return await asyncio.to_thread(_cpu_usage_sync, pid)


def _cpu_usage_sync(pid: int) -> float:
    try:
        process = process_obj_cache.get(pid, psutil.Process(pid))
        process_obj_cache[pid] = process
        return process.cpu_percent(1)
    except NoSuchProcess:
        return 0.0
