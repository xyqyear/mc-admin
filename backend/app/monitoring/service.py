import asyncio
import hashlib
import time
from collections.abc import Awaitable, Callable

import psutil
from docker.errors import DockerException
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from yaml import YAMLError

from ..errors import log_safe_error
from ..minecraft.docker.cgroup import read_block_io_stats, read_memory_stats
from ..minecraft.docker.network import read_network_stats
from ..minecraft.docker.reader import ContainerState, DockerReader
from ..minecraft.manager import DockerMCManager
from ..minecraft.paths import resolve_server_paths
from ..operations.finalization import finalize
from ..runtime_resources import spawn_background
from ..servers.crud import get_active_servers
from ..servers.references import ServerRef, revalidate_server_ref
from ..system.resources import get_disk_info
from .cpu import ProcessCounter, read_process_counter, system_cpu_percent
from .models import (
    ByteCounters,
    DiskUsage,
    MemoryUsage,
    Sample,
    ServerSamples,
    SystemSamples,
)

READ_ERRORS = (OSError, RuntimeError, ValueError, LookupError, TypeError, psutil.Error,
               DockerException, HTTPException, SQLAlchemyError, YAMLError)


class RuntimeMonitor:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], minecraft: DockerMCManager,
        docker: DockerReader, *, interval: float = 2, disk_interval: float = 60,
    ) -> None:
        self._sessions = session_factory
        self._minecraft = minecraft
        self._docker = docker
        self._interval = interval
        self._disk_interval = disk_interval
        self.system = SystemSamples()
        self.servers: dict[int, ServerSamples] = {}
        self._processes: dict[int, ProcessCounter] = {}
        self._system_cpu: dict[str, float] | None = None
        self._disk_due: dict[int, float] = {}
        self._workers: list[asyncio.Task[None]] = []
        self._closed = False
        self._close_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._closed:
            raise RuntimeError("监控服务已关闭")
        if not self._workers:
            self._workers = [
                spawn_background(self._repeat(self.sample_system), name="monitor-system"),
                spawn_background(self._repeat(self.sample_servers), name="monitor-servers"),
                spawn_background(self._repeat(self.sample_disks), name="monitor-disks"),
            ]

    async def _repeat(self, sample: Callable[[], Awaitable[None]]) -> None:
        while not self._closed:
            started = time.monotonic()
            try:
                await sample()
            except Exception as error:
                if self._closed:
                    raise
                log_safe_error(error, "Monitoring collection failed")
            await asyncio.sleep(max(self._interval - (time.monotonic() - started), 0.05))

    async def close(self) -> None:
        if self._close_task is None:
            self._closed = True
            self._close_task = asyncio.create_task(self._close(), name="monitor-close")
        await finalize(self._close_task)

    async def _close(self) -> None:
        self._closed = True
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            results = await asyncio.gather(*self._workers, return_exceptions=True)
            errors = [result for result in results if isinstance(result, Exception)]
            if errors:
                raise ExceptionGroup("监控采样清理失败", errors)
        self._workers.clear()

    async def identities(self) -> dict[str, int]:
        async with self._sessions() as session:
            return {row.server_id: row.id for row in await get_active_servers(session)}

    async def _reference(self, server_id: str, generation: int) -> ServerRef:
        paths = await resolve_server_paths(self._minecraft.servers_path, server_id)
        return ServerRef(server_id, generation, paths.servers_root, paths.project_path, paths.data_path)

    async def _current(self, reference: ServerRef) -> bool:
        try:
            async with self._sessions() as session:
                await revalidate_server_ref(session, reference, require_exists=False)
            return True
        except READ_ERRORS:
            return False

    async def sample_system(self) -> None:
        try:
            counters = await finalize(asyncio.to_thread(lambda: psutil.cpu_times()._asdict()))
            percent = system_cpu_percent(counters, self._system_cpu)
            self._system_cpu = counters
            self.system.cpu_percent = Sample[float]() if percent is None else Sample.ready(percent)
        except READ_ERRORS:
            self.system.cpu_percent = self.system.cpu_percent.failed("无法读取宿主机 CPU")
        try:
            memory = await finalize(asyncio.to_thread(psutil.virtual_memory))
            self.system.memory = Sample.ready(MemoryUsage(used=memory.used, total=memory.total))
        except READ_ERRORS:
            self.system.memory = self.system.memory.failed("无法读取宿主机内存")
        try:
            self.system.load = Sample.ready(await finalize(asyncio.to_thread(psutil.getloadavg)))
        except READ_ERRORS:
            self.system.load = self.system.load.failed("无法读取宿主机负载")
        try:
            disk = await get_disk_info(self._minecraft.servers_path)
            self.system.disk = Sample.ready(DiskUsage(used=disk.used, total=disk.total, available=disk.available))
        except READ_ERRORS:
            self.system.disk = self.system.disk.failed("无法读取磁盘容量")

    async def sample_servers(self) -> None:
        identities = await self.identities()
        active = set(identities.values())
        for generation in self.servers.keys() - active:
            self.servers.pop(generation)
        for generation in self._processes.keys() - active:
            self._processes.pop(generation, None)
        for generation in self._disk_due.keys() - active:
            self._disk_due.pop(generation, None)
        for generation in active:
            self.servers.setdefault(generation, ServerSamples(generation=generation))
        if not identities:
            return
        try:
            containers = await self._docker.list_containers()
        except READ_ERRORS:
            for samples in self.servers.values():
                samples.fail_runtime("无法读取 Docker 状态")
            return
        for server_id, generation in identities.items():
            original = self.servers[generation]
            samples = original.model_copy(deep=True)
            try:
                reference = await self._reference(server_id, generation)
                instance = self._minecraft.get_instance(server_id)
                if not await instance.exists():
                    samples.fail_runtime("服务器配置缺失")
                else:
                    state = await self._docker.observe(await instance.get_project_target(), containers)
                    container = state.container
                    incarnation = hashlib.sha256(container.identity.encode()).hexdigest()[:24] if container else None
                    if samples.incarnation != incarnation:
                        self._processes.pop(generation, None)
                        samples = ServerSamples(generation=generation, incarnation=incarnation, disk=original.disk)
                    samples.status = Sample.ready(state.status)
                    if container is None or not container.running:
                        self._processes.pop(generation, None)
                        samples.cpu_percent = Sample[float]().failed("服务器未运行")
                        samples.memory_bytes = Sample[int]().failed("服务器未运行")
                        samples.disk_io = Sample[ByteCounters]().failed("服务器未运行")
                        samples.network_io = Sample[ByteCounters]().failed("服务器未运行")
                    else:
                        await self._sample_container(samples, container)
                if not await self._current(reference):
                    self._processes.pop(generation, None)
                    continue
            except READ_ERRORS:
                samples.fail_runtime("无法读取服务器状态或配置")
            # The independent disk worker may have published while these reads were in flight.
            samples.disk = self.servers[generation].disk
            self.servers[generation] = samples

    async def _sample_container(self, samples: ServerSamples, container: ContainerState) -> None:
        previous = self._processes.get(samples.generation)
        counter = None
        try:
            if previous is not None:
                try:
                    counter = await finalize(asyncio.to_thread(read_process_counter, previous.pid, container.container_id))
                except (OSError, RuntimeError, psutil.Error):
                    previous = None
            if counter is None:
                pid = await self._docker.java_pid(container.container_id)
                counter = await finalize(asyncio.to_thread(read_process_counter, pid, container.container_id))
            percent = counter.percent_since(previous)
            self._processes[samples.generation] = counter
            samples.cpu_percent = Sample[float]() if percent is None else Sample.ready(percent)
        except READ_ERRORS:
            self._processes.pop(samples.generation, None)
            samples.cpu_percent = samples.cpu_percent.failed("无法读取 Java CPU")
        try:
            memory = await read_memory_stats(container.container_id)
            samples.memory_bytes = Sample.ready(memory.total_memory)
        except READ_ERRORS:
            samples.memory_bytes = samples.memory_bytes.failed("无法读取容器内存")
        try:
            disk = await read_block_io_stats(container.container_id)
            samples.disk_io = Sample.ready(ByteCounters(read=disk.total_read_bytes, write=disk.total_write_bytes))
        except READ_ERRORS:
            samples.disk_io = samples.disk_io.failed("无法读取磁盘 I/O")
        try:
            if counter is None:
                raise RuntimeError("Java 进程不可用")
            network = await read_network_stats(counter.pid)
            samples.network_io = Sample.ready(ByteCounters(read=network.total_rx_bytes, write=network.total_tx_bytes))
        except READ_ERRORS:
            samples.network_io = samples.network_io.failed("无法读取网络 I/O")

    async def sample_disks(self) -> None:
        for server_id, generation in (await self.identities()).items():
            if time.monotonic() < self._disk_due.get(generation, 0):
                continue
            samples = self.servers.setdefault(generation, ServerSamples(generation=generation))
            try:
                reference = await self._reference(server_id, generation)
                disk = await self._minecraft.get_instance(server_id).get_disk_space_info()
                value = Sample.ready(DiskUsage(used=disk.used_bytes, total=disk.total_bytes, available=disk.available_bytes))
                if await self._current(reference) and generation in self.servers:
                    self.servers[generation].disk = value
            except READ_ERRORS:
                if generation in self.servers:
                    self.servers[generation].disk = samples.disk.failed("无法统计存档目录占用")
            finally:
                self._disk_due[generation] = time.monotonic() + self._disk_interval
