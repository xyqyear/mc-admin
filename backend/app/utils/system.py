"""
System monitoring utilities for process CPU and memory usage.
"""

import psutil
from asyncer import asyncify
from psutil import NoSuchProcess, Process

# Global process object cache for efficiency
process_obj_cache = dict[int, Process]()


@asyncify
def get_process_memory_usage(pid: int) -> int:
    """
    Get the memory usage of a process by its PID in bytes.

    Args:
        pid: Process ID

    Returns:
        Memory usage in bytes (RSS - Resident Set Size)
        Returns 0 if process doesn't exist
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
    Get the CPU usage of a process by its PID in percentage.

    Note: This function blocks for 1 second to calculate CPU usage.

    Args:
        pid: Process ID

    Returns:
        CPU usage as percentage (0.0-100.0)
        Returns 0.0 if process doesn't exist
    """
    try:
        process = process_obj_cache.get(pid, psutil.Process(pid))
        process_obj_cache[pid] = process
        return process.cpu_percent(1)
    except NoSuchProcess:
        return 0.0
