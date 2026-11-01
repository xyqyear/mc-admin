import time
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from ..minecraft.status import MCServerStatus
from ..servers.api_models import ServerMaintenance


class Sample[T](BaseModel):
    model_config = ConfigDict(frozen=True)

    value: T | None = None
    sampled_at: datetime | None = None
    quality: Literal["ready", "pending", "stale", "unavailable"] = "pending"
    error: str | None = None
    _captured_at: float = PrivateAttr(default_factory=time.monotonic)

    @classmethod
    def ready(cls, value: T) -> Self:
        return cls(value=value, sampled_at=datetime.now(UTC), quality="ready")

    def failed(self, message: str) -> Self:
        return self.model_copy(update={
            "quality": "stale" if self.value is not None else "unavailable", "error": message,
        })

    def view(self, max_age: float = 6) -> Self:
        if self.quality == "ready" and time.monotonic() - self._captured_at > max_age:
            return self.model_copy(update={"quality": "stale", "error": "等待更新监控数据"})
        return self


class ByteCounters(BaseModel):
    read: int
    write: int


class MemoryUsage(BaseModel):
    used: int
    total: int


class DiskUsage(MemoryUsage):
    available: int


class SystemSamples(BaseModel):
    cpu_percent: Sample[float] = Field(default_factory=Sample[float])
    memory: Sample[MemoryUsage] = Field(default_factory=Sample[MemoryUsage])
    load: Sample[tuple[float, float, float]] = Field(default_factory=Sample[tuple[float, float, float]])
    disk: Sample[DiskUsage] = Field(default_factory=Sample[DiskUsage])

    def view(self) -> Self:
        return self.model_copy(update={name: getattr(self, name).view() for name in type(self).model_fields})


class ServerSamples(BaseModel):
    generation: int
    incarnation: str | None = None
    status: Sample[MCServerStatus] = Field(default_factory=Sample[MCServerStatus])
    cpu_percent: Sample[float] = Field(default_factory=Sample[float])
    memory_bytes: Sample[int] = Field(default_factory=Sample[int])
    disk_io: Sample[ByteCounters] = Field(default_factory=Sample[ByteCounters])
    network_io: Sample[ByteCounters] = Field(default_factory=Sample[ByteCounters])
    disk: Sample[DiskUsage] = Field(default_factory=Sample[DiskUsage])
    maintenance: ServerMaintenance = Field(default_factory=ServerMaintenance)

    def view(self, maintenance: ServerMaintenance) -> Self:
        return self.model_copy(update={
            "maintenance": maintenance, "status": self.status.view(),
            "cpu_percent": self.cpu_percent.view(), "memory_bytes": self.memory_bytes.view(),
            "disk_io": self.disk_io.view(), "network_io": self.network_io.view(), "disk": self.disk.view(120),
        })

    def fail_runtime(self, message: str) -> None:
        self.status = self.status.failed(message)
        self.cpu_percent = self.cpu_percent.failed(message)
        self.memory_bytes = self.memory_bytes.failed(message)
        self.disk_io = self.disk_io.failed(message)
        self.network_io = self.network_io.failed(message)


class MonitoringSnapshot(BaseModel):
    system: SystemSamples
    servers: dict[str, ServerSamples]
