"""Run only inside the Go runner's owned base fixture; output contains no credentials."""

import argparse
import asyncio
import json
import os
import re
import signal
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx2 as httpx


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def percentile(values, fraction):
    return sorted(values)[min(len(values) - 1, int(len(values) * fraction))] if values else None


class Benchmark:
    def __init__(self, mode, seconds):
        fixture_path = Path(os.environ["MC_ADMIN_BROWSER_FIXTURE"])
        self.fixture = json.loads(fixture_path.read_text())
        self.output = Path(self.fixture["manifest_path"]).parent / "benchmark.json"
        self.mode = mode
        self.seconds = seconds
        self.ids = []
        self.results = []
        self.traces = []
        self.client = httpx.AsyncClient(base_url=self.fixture["base_url"],
                                       headers={"Authorization": "Bearer " + self.fixture["master_token"]},
                                       timeout=60, limits=httpx.Limits(max_connections=500))
        self.pid = int(docker("inspect", "--format", "{{.State.Pid}}", self.fixture["backend_container"]))
        relative = Path(f"/proc/{self.pid}/cgroup").read_text().strip().split("::", 1)[1]
        self.cgroup = Path("/sys/fs/cgroup") / relative.lstrip("/")

    async def json(self, method, path, body=None):
        response = await self.client.request(method, "/api" + path, json=body)
        if not response.is_success:
            raise RuntimeError(f"{method} {path}: HTTP {response.status_code}")
        return response.json()

    async def task(self, path, body):
        accepted = await self.json("POST", path, body)
        async with asyncio.timeout(240):
            while True:
                task = await self.json("GET", "/tasks/" + accepted["task_id"])
                if task["status"] == "completed":
                    return
                if task["status"] in {"failed", "cancelled"}:
                    raise RuntimeError(f"Task failed: {path}")
                await asyncio.sleep(0.25)

    async def add_server(self):
        index = len(self.ids)
        env = self.fixture["environment_id"]
        name = f"bench-{env}-{index}"
        self.ids.append(name)
        with socket.socket() as game, socket.socket() as rcon:
            game.bind(("127.0.0.1", 0))
            rcon.bind(("127.0.0.1", 0))
            game_port, rcon_port = game.getsockname()[1], rcon.getsockname()[1]
        compose = f"""name: perf-{env}-{index}
services:
  mc:
    image: itzg/minecraft-server:java25-issue150-offline
    container_name: mc-{name}
    network_mode: bridge
    labels:
      io.mc-admin.e2e.run: {self.fixture['run_id']}
      io.mc-admin.e2e.environment: {env}
    environment:
      EULA: 'true'
      VERSION: '1.21.11'
      TYPE: VANILLA
      SERVER_PORT: '25565'
      ENABLE_RCON: 'true'
      RCON_PASSWORD: {self.fixture['password']}
      ONLINE_MODE: 'false'
      INIT_MEMORY: 256M
      MAX_MEMORY: 768M
      VIEW_DISTANCE: '2'
      SIMULATION_DISTANCE: '2'
      LEVEL_TYPE: minecraft:flat
      GENERATE_STRUCTURES: 'false'
      SPAWN_PROTECTION: '0'
      UID: '0'
      GID: '0'
    ports:
      - '127.0.0.1:{game_port}:25565'
      - '127.0.0.1:{rcon_port}:25575'
    volumes:
      - ./data:/data
    stdin_open: true
    tty: true
    restart: 'no'
"""
        ownership = self.output.parent / "benchmark-ownership.json"
        ownership.write_text(json.dumps({"run_id": self.fixture["run_id"], "environment_id": env,
                                         "containers": ["mc-" + name for name in self.ids]}))
        await self.task("/servers/" + name, {"yaml_content": compose})
        await self.task(f"/servers/{name}/operations", {"action": "up"})
        async with asyncio.timeout(240):
            while True:
                health = await asyncio.to_thread(docker, "inspect", "--format", "{{.State.Health.Status}}", "mc-" + name)
                if health == "healthy":
                    break
                await asyncio.sleep(1)
        print(f"{self.mode}: {len(self.ids)} real servers ready", flush=True)

    def resources(self):
        cpu = dict(line.split() for line in (self.cgroup / "cpu.stat").read_text().splitlines())
        return {"cpu_seconds": int(cpu["usage_usec"]) / 1e6,
                "fds": len(list(Path(f"/proc/{self.pid}/fd").iterdir())),
                "threads": len(list(Path(f"/proc/{self.pid}/task").iterdir())),
                "processes": len((self.cgroup / "cgroup.procs").read_text().splitlines())}

    def streams(self):
        if self.mode == "candidate":
            return [("/monitoring", 2)]
        result = [("/system/cpu_percent", 3), ("/system/info", 10), ("/system/disk-usage", 30)]
        for name in self.ids:
            result.extend((f"/servers/{name}/{suffix}", interval) for suffix, interval in
                          [("status", 5), ("status", 5), ("cpu_percent", 3), ("memory", 3),
                           ("maintenance", 1), ("disk-usage", 30)])
        return result

    async def measure(self, observers, concurrent=False, *, diagnostic=False):
        latencies, health_latencies, errors, ages = [], [], [], []
        sample_times = set()
        started = time.monotonic()
        end = started + self.seconds
        before = self.resources()

        async def stream(path, interval, output, offset):
            await asyncio.sleep(offset)
            while time.monotonic() < end:
                requested = time.monotonic()
                try:
                    data = await self.json("GET", path)
                    output.append((time.monotonic() - requested) * 1000)
                    if path == "/monitoring":
                        now = datetime.now(UTC)
                        for server in data["servers"].values():
                            sample = server["cpu_percent"]
                            if sample["sampled_at"]:
                                stamp = datetime.fromisoformat(sample["sampled_at"].replace("Z", "+00:00"))
                                ages.append((now - stamp).total_seconds())
                                sample_times.add((server["generation"], sample["sampled_at"]))
                except (httpx.HTTPError, RuntimeError) as error:
                    errors.append(type(error).__name__)
                await asyncio.sleep(max(0, min(interval, end - time.monotonic())))

        async def operation():
            await asyncio.sleep(3)
            await self.task(f"/servers/{self.ids[0]}/operations", {"action": "restart"})

        workers = [stream(path, interval, latencies, observer * 0.07)
                   for observer in range(observers) for path, interval in self.streams()]
        workers.append(stream("/system/health", 0.2, health_latencies, 0))
        if concurrent:
            workers.append(operation())
        await asyncio.gather(*workers)
        after = self.resources()
        elapsed = time.monotonic() - started
        await asyncio.sleep(3)
        drained = self.resources()
        result = {"servers": len(self.ids), "observers": observers, "concurrent_restart": concurrent,
                  "seconds": elapsed, "admin_cpu_percent": (after["cpu_seconds"] - before["cpu_seconds"]) / elapsed * 100,
                  "requests": len(latencies), "errors": errors, "p50_ms": percentile(latencies, 0.5),
                  "p95_ms": percentile(latencies, 0.95), "health_p95_ms": percentile(health_latencies, 0.95),
                  "cpu_sample_age_p95_seconds": percentile(ages, 0.95), "unique_cpu_samples": len(sample_times),
                  "diagnostic_tracing": diagnostic,
                  "before": before, "after": after, "drained": drained}
        self.results.append(result)
        self.save()
        print(json.dumps({key: value for key, value in result.items() if key not in {"before", "after", "drained"}}), flush=True)

    async def trace(self, observers):
        private = self.output.parent / "runtime" / f"monitor-{observers}.trace"
        private.touch(mode=0o600)
        started = time.monotonic()
        process = subprocess.Popen(["strace", "-f", "-qq", "-yy", "-s", "128", "-e",
                                    "trace=execve,getdents64,write,sendto", "-p", str(self.pid), "-o", str(private)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        original = self.seconds
        try:
            self.seconds = 10
            await self.measure(observers, diagnostic=True)
        finally:
            self.seconds = original
            process.send_signal(signal.SIGINT)
            await asyncio.to_thread(process.wait, 10)
        lines = private.read_text().splitlines()
        if not lines:
            raise RuntimeError("Tracing did not produce observations")
        self.traces.append({"observers": observers, "seconds": time.monotonic() - started,
                            "successful_execs": sum("execve(" in line and line.endswith("= 0") for line in lines),
                            "compose_execs": sum('execve(' in line and 'docker-compose"' in line and line.endswith("= 0") for line in lines),
                            "proc_directory_batches": sum(bool(re.search(r'getdents64\(\d+</proc>,.*= [1-9]', line)) for line in lines),
                            "engine_gets": sum(bool(re.search(r'"GET /v[0-9.]+/(containers|info|version)', line)) for line in lines)})
        self.save()
        print(json.dumps(self.traces[-1]), flush=True)

    def save(self):
        self.output.write_text(json.dumps({"mode": self.mode, "image": self.fixture["image_id"],
                                          "run_id": self.fixture["run_id"], "results": self.results,
                                          "traces": self.traces}, indent=2))

    async def run(self, restart_only=False):
        try:
            for count in ((6,) if restart_only else (1, 6)):
                while len(self.ids) < count:
                    await self.add_server()
                await asyncio.sleep(10)
                if not restart_only:
                    for observers in (0, 1, 10):
                        await self.measure(observers)
            await self.measure(1, concurrent=True)
            if not restart_only:
                await self.trace(1)
                await self.trace(10)
        finally:
            self.save()
            failures = []
            for name in self.ids:
                try:
                    await self.task(f"/servers/{name}/operations", {"action": "down"})
                except Exception as error:
                    failures.append(type(error).__name__)
            await self.client.aclose()
            if failures:
                raise RuntimeError(f"API cleanup failed; owned runner must drain containers: {failures}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["baseline", "candidate"], required=True)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--restart-only", action="store_true")
    args = parser.parse_args()
    asyncio.run(Benchmark(args.mode, args.seconds).run(args.restart_only))
