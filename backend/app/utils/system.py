"""Per-process CPU queries via psutil, off-loaded to threads."""

import asyncio

import psutil
from psutil import NoSuchProcess


async def get_process_cpu_usage(pid: int) -> float:
    """One-second per-process CPU sample; may exceed 100 on multiple cores."""
    return await asyncio.to_thread(_cpu_usage_sync, pid)


def _cpu_usage_sync(pid: int) -> float:
    try:
        process = psutil.Process(pid)
        return process.cpu_percent(1)
    except NoSuchProcess:
        return 0.0
