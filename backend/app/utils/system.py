"""
System monitoring utilities for process CPU and memory usage.
"""

import asyncio

import psutil
from psutil import NoSuchProcess, Process

# Global process object cache for efficiency
process_obj_cache = dict[int, Process]()


async def get_process_memory_usage(pid: int) -> int:
    """Get the memory usage of a process by its PID in bytes (RSS).

    Returns 0 if the process does not exist.
    """
    return await asyncio.to_thread(_memory_usage_sync, pid)


def _memory_usage_sync(pid: int) -> int:
    try:
        process = process_obj_cache.get(pid, psutil.Process(pid))
        process_obj_cache[pid] = process
        return process.memory_info().rss
    except NoSuchProcess:
        return 0


async def get_process_cpu_usage(pid: int) -> float:
    """Get the CPU usage of a process by its PID as a percentage (0.0-100.0).

    Note: blocks for 1 second on the worker thread to compute the delta.
    Returns 0.0 if the process does not exist.
    """
    return await asyncio.to_thread(_cpu_usage_sync, pid)


def _cpu_usage_sync(pid: int) -> float:
    try:
        process = process_obj_cache.get(pid, psutil.Process(pid))
        process_obj_cache[pid] = process
        return process.cpu_percent(1)
    except NoSuchProcess:
        return 0.0
