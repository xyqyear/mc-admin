import asyncio
import json
import os
import time
from datetime import UTC, datetime

import httpx2 as httpx
import pytest

from app.main import create_api_app
from app.minecraft.docker.reader import ContainerState, ProjectState
from app.minecraft.instance import DiskSpaceInfo, MCInstance
from app.minecraft.status import MCServerStatus
from app.monitoring.cpu import ProcessCounter, system_cpu_percent
from app.monitoring.models import Sample
from app.routers.monitoring import get_monitoring
from app.servers.crud import create_server_record, mark_server_removed
from app.world.locks import LockHolder, ServerOperationKind
from tests.fixtures.test_utils import create_mc_server_compose_yaml
from tests.support.runtime import set_runtime_resource


class ObservedEngine:
    def __init__(self):
        self.observations = 0
        self.failure = False
        self.container = ContainerState("a" * 64, "first-start", True, "healthy")

    async def list_containers(self):
        if self.failure:
            raise ConnectionError("offline")
        self.observations += 1
        return []

    async def observe(self, target, containers=None):
        return ProjectState(MCServerStatus.HEALTHY if self.container.running else MCServerStatus.CREATED, self.container)

    async def java_pid(self, container_id):
        return os.getpid()

    async def close(self):
        pass


@pytest.fixture
async def monitored(database, isolated_runtime, monkeypatch):
    engine = ObservedEngine()
    set_runtime_resource(monkeypatch, "docker_reader", engine)
    server = isolated_runtime.docker_mc_manager.get_instance("alpha")
    await server.create(create_mc_server_compose_yaml("alpha", 25565, 25575))
    async with database.session_factory() as session:
        record = await create_server_record(session, "alpha")
    cgroup = isolated_runtime.settings.server_path.parent / "cgroup"
    isolated_runtime.settings.cgroup_path = cgroup
    group = cgroup / f"system.slice/docker-{engine.container.container_id}.scope"
    group.mkdir(parents=True)
    (group / "memory.stat").write_text("anon 100\nfile 200\nkernel 50\n")
    (group / "io.stat").write_text("8:0 rbytes=1000 wbytes=2000\n")
    counters = iter([ProcessCounter(os.getpid(), 10, n * 4, n * 2) for n in range(1, 100)])
    monkeypatch.setattr("app.monitoring.service.read_process_counter", lambda *args: next(counters))
    return isolated_runtime.monitor, engine, record.id, isolated_runtime


def test_cpu_intervals_preserve_multicore_and_reset_identity():
    previous = ProcessCounter(10, 100, 4, 20)
    assert ProcessCounter(10, 100, 11, 24).percent_since(previous) == 175
    assert ProcessCounter(10, 100, 4, 24).percent_since(previous) == 0
    assert ProcessCounter(10, 101, 11, 24).percent_since(previous) is None
    assert ProcessCounter(11, 100, 11, 24).percent_since(previous) is None
    assert ProcessCounter(10, 100, 3, 24).percent_since(previous) is None
    assert ProcessCounter(10, 100, 11, 20).percent_since(previous) is None
    assert previous.percent_since(None) is None


def test_system_cpu_excludes_guest_double_counting_and_iowait():
    previous = {"user": 10, "system": 5, "idle": 30, "iowait": 2, "guest": 2, "guest_nice": 0}
    current = {"user": 16, "system": 7, "idle": 38, "iowait": 6, "guest": 4, "guest_nice": 0}
    assert system_cpu_percent(current, previous) == 40
    assert system_cpu_percent(current, None) is None
    assert system_cpu_percent(current, current) is None
    assert system_cpu_percent({**previous, "user": 9, "idle": 32}, previous) == 0


async def test_shared_samples_preserve_meaning_and_do_not_resample_on_read(monitored):
    monitor, engine, generation, _ = monitored
    await monitor.sample_servers()
    first = await get_monitoring()
    assert first.servers["alpha"].cpu_percent.quality == "pending"
    await monitor.sample_servers()
    second = await get_monitoring()
    current = second.servers["alpha"]
    assert current.cpu_percent.value == 200
    assert current.memory_bytes.value == 300
    assert current.disk_io.value is not None
    assert current.disk_io.value.read == 1000
    assert current.disk_io.value.write == 2000
    assert current.generation == generation
    reads = await asyncio.gather(*(get_monitoring() for _ in range(20)))
    assert all(result.servers["alpha"].cpu_percent.sampled_at == current.cpu_percent.sampled_at for result in reads)
    assert engine.observations == 2


async def test_failures_are_stale_and_host_remains_available(monitored):
    monitor, engine, generation, _ = monitored
    await monitor.sample_servers()
    await monitor.sample_servers()
    previous = monitor.servers[generation].cpu_percent
    engine.failure = True
    await monitor.sample_servers()
    await monitor.sample_system()
    result = await get_monitoring()
    assert result.servers["alpha"].status.value == MCServerStatus.HEALTHY
    assert result.servers["alpha"].status.quality == "stale"
    assert result.servers["alpha"].cpu_percent.sampled_at == previous.sampled_at
    assert result.system.memory.value is not None and result.system.memory.value.total > 0
    engine.failure = False
    await monitor.sample_servers()
    assert (await get_monitoring()).servers["alpha"].status.quality == "ready"


async def test_broken_configuration_only_degrades_its_own_samples(monitored, database):
    monitor, _, _, runtime = monitored
    broken = runtime.docker_mc_manager.servers_path / "broken"
    broken.mkdir()
    (broken / "docker-compose.yml").write_text("services: [invalid")
    async with database.session_factory() as session:
        await create_server_record(session, "broken")
    await monitor.sample_servers()
    await monitor.sample_system()
    result = await get_monitoring()
    assert result.servers["alpha"].status.value == MCServerStatus.HEALTHY
    assert result.servers["broken"].status.value is None
    assert result.servers["broken"].status.quality == "unavailable"
    assert result.system.memory.quality == "ready"


@pytest.mark.parametrize("server_count", [1, 6, 20])
@pytest.mark.parametrize("observers", [1, 10])
async def test_observer_scaling_does_not_multiply_engine_work(monitored, database, monkeypatch, server_count, observers):
    monitor, engine, _, runtime = monitored
    for index in range(1, server_count):
        name = f"scale-{index}"
        await runtime.docker_mc_manager.get_instance(name).create(create_mc_server_compose_yaml(name, 25565, 25575))
        async with database.session_factory() as session:
            await create_server_record(session, name)
    observations = 0
    observe = engine.observe

    async def counted(*args, **kwargs):
        nonlocal observations
        observations += 1
        return await observe(*args, **kwargs)

    monkeypatch.setattr(engine, "observe", counted)
    delays = []
    running = True

    async def heartbeat():
        while running:
            start = time.monotonic()
            await asyncio.sleep(0.005)
            delays.append(max(0, time.monotonic() - start - 0.005) * 1000)

    ticker = asyncio.create_task(heartbeat())
    try:
        await monitor.sample_servers()
        await monitor.sample_servers()
        original = await get_monitoring()
        for _ in range(5):
            snapshots = await asyncio.gather(*(get_monitoring() for _ in range(observers)))
            assert all(snapshot == original for snapshot in snapshots)
    finally:
        running = False
        await ticker
    assert len(original.servers) == server_count
    assert engine.observations == 2
    assert observations == server_count * 2
    print(json.dumps({"simulated_servers": server_count, "observers": observers,
                      "reads": observers * 5 + 1, "list_calls": engine.observations,
                      "project_observations": observations,
                      "loop_delay_p95_ms": sorted(delays)[int((len(delays) - 1) * 0.95)]}))


async def test_age_advances_without_successful_collection(monitored):
    monitor, _, generation, _ = monitored
    await monitor.sample_servers()
    original = monitor.servers[generation].status
    original._captured_at -= 7
    current = (await get_monitoring()).servers["alpha"].status
    assert current.quality == "stale"
    assert current.sampled_at == original.sampled_at
    assert "_captured_at" not in current.model_dump()


async def test_restart_and_stop_reset_samples(monitored):
    monitor, engine, _, _ = monitored
    await monitor.sample_servers()
    await monitor.sample_servers()
    first = (await get_monitoring()).servers["alpha"]
    engine.container = ContainerState(engine.container.container_id, "second-start", True, "healthy")
    await monitor.sample_servers()
    restarted = (await get_monitoring()).servers["alpha"]
    assert restarted.incarnation != first.incarnation
    assert restarted.cpu_percent.quality == "pending"
    engine.container = ContainerState(engine.container.container_id, "second-start", False, "")
    await monitor.sample_servers()
    stopped = (await get_monitoring()).servers["alpha"]
    assert stopped.status.value == MCServerStatus.CREATED
    assert stopped.cpu_percent.value is None and stopped.memory_bytes.value is None
    assert stopped.cpu_percent.quality == "unavailable"


async def test_generation_replacement_rejects_late_disk_result(monitored, database, monkeypatch):
    monitor, _, generation, _ = monitored
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow_disk(self):
        entered.set()
        await release.wait()
        return DiskSpaceInfo(999, 1000, 1)

    monkeypatch.setattr(MCInstance, "get_disk_space_info", slow_disk)
    pending = asyncio.create_task(monitor.sample_disks())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await monitor.sample_servers()
        async with database.session_factory() as session:
            await mark_server_removed(session, "alpha", datetime.now(UTC))
            replacement = await create_server_record(session, "alpha")
        current = await get_monitoring()
        assert current.servers["alpha"].generation == replacement.id != generation
        assert current.servers["alpha"].disk.quality == "pending"
    finally:
        release.set()
        await pending
    assert (await get_monitoring()).servers["alpha"].disk.value is None


async def test_maintenance_is_current_before_sampling_or_terminal_event(monitored):
    _, _, _, runtime = monitored
    lock = runtime.server_operation_lock
    holder = LockHolder(ServerOperationKind.RESTORE, datetime.now(UTC), None, "正在恢复")
    assert not (await get_monitoring()).servers["alpha"].maintenance.active
    async with lock.acquire("alpha", holder):
        result = (await get_monitoring()).servers["alpha"].maintenance
        assert result.active and result.kind == "restore" and result.description == "正在恢复"
    assert not (await get_monitoring()).servers["alpha"].maintenance.active


async def test_recovery_reason_takes_priority_and_keeps_command_admission_blocked(monitored):
    from fastapi import HTTPException

    _, _, _, runtime = monitored
    with runtime.server_write_admission.freeze("alpha"):
        runtime.server_write_admission.block("alpha", "写入停止尚未确认")
        status = (await get_monitoring()).servers["alpha"].maintenance
        assert status.active and status.kind == "recovery"
        assert status.description == "写入停止尚未确认"
        with pytest.raises(HTTPException) as error:
            runtime.server_write_admission.check("alpha")
        assert error.value.status_code == 423
        runtime.server_write_admission.unblock("alpha")
        assert (await get_monitoring()).servers["alpha"].maintenance.kind == "remove"


async def test_slow_docker_does_not_queue_rounds_or_block_host_samples(monitored, monkeypatch):
    monitor, engine, _, _ = monitored
    monitor._interval = 0.01
    entered, drained = asyncio.Event(), asyncio.Event()
    reads = 0

    async def slow_engine():
        nonlocal reads
        reads += 1
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            drained.set()

    monkeypatch.setattr(engine, "list_containers", slow_engine)
    monitor.start()
    try:
        await asyncio.wait_for(entered.wait(), 2)
        async with asyncio.timeout(2):
            while monitor.system.cpu_percent.quality != "ready":
                await asyncio.sleep(0.01)
        snapshot = await asyncio.wait_for(get_monitoring(), 2)
        assert snapshot.system.memory.value is not None
        assert snapshot.servers["alpha"].status.quality == "pending"
        assert reads == 1
    finally:
        await monitor.close()
    assert drained.is_set()


async def test_slow_directory_does_not_block_observation_and_is_drained_on_close(monitored, monkeypatch):
    monitor, _, _, _ = monitored
    entered, cleaned = asyncio.Event(), asyncio.Event()

    async def slow_disk(self):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    monkeypatch.setattr(MCInstance, "get_disk_space_info", slow_disk)
    monitor.start()
    try:
        await asyncio.wait_for(entered.wait(), 2)
        result = await asyncio.wait_for(get_monitoring(), 2)
        assert result.servers["alpha"].disk.quality == "pending"
    finally:
        await monitor.close()
    assert cleaned.is_set()


async def test_monitoring_rejects_unauthenticated_reads(isolated_runtime):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_api_app(isolated_runtime)), base_url="http://test") as client:
        response = await client.get("/monitoring")
    assert response.status_code == 401


def test_failed_sample_never_becomes_zero_or_refreshes_timestamp():
    first = Sample.ready(25.0)
    failed = first.failed("采样失败")
    assert failed.value == 25 and failed.sampled_at == first.sampled_at
    assert failed.quality == "stale"
    assert Sample[float]().failed("采样失败").quality == "unavailable"
