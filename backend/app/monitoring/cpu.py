import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import psutil


@dataclass(frozen=True)
class ProcessCounter:
    pid: int
    started_at: float
    seconds: float
    observed_at: float

    def percent_since(self, previous: "ProcessCounter | None") -> float | None:
        if previous is None or (self.pid, self.started_at) != (previous.pid, previous.started_at):
            return None
        elapsed = self.observed_at - previous.observed_at
        used = self.seconds - previous.seconds
        if elapsed <= 0 or used < 0:
            return None
        return used / elapsed * 100


def read_process_counter(pid: int, container_id: str) -> ProcessCounter:
    process = psutil.Process(pid)
    with process.oneshot():
        started_at = process.create_time()
        if process.name() != "java" or container_id not in Path(f"/proc/{pid}/cgroup").read_text():
            raise RuntimeError("Java 进程归属已变更")
        cpu = process.cpu_times()
        counter = ProcessCounter(pid, started_at, cpu.user + cpu.system, time.monotonic())
    if not process.is_running():
        raise RuntimeError("Java 进程已退出")
    return counter


def system_cpu_percent(current: Mapping[str, float], previous: Mapping[str, float] | None) -> float | None:
    if previous is None or current.keys() != previous.keys():
        return None
    delta = {key: max(0, value - previous[key]) for key, value in current.items()}
    total = sum(delta.values()) - delta.get("guest", 0) - delta.get("guest_nice", 0)
    if total <= 0:
        return None
    busy = total - delta.get("idle", 0) - delta.get("iowait", 0)
    return round(max(0, min(100, busy / total * 100)), 1)
