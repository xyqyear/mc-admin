from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal
from uuid import uuid4


class OperationState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    FINALIZING = "finalizing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    SKIPPED = "skipped"


TERMINAL_STATES = frozenset({
    OperationState.SUCCEEDED, OperationState.FAILED, OperationState.CANCELLED,
    OperationState.INTERRUPTED, OperationState.SKIPPED,
})


@dataclass(frozen=True)
class ResourceReference:
    kind: str
    server_id: str | None = None
    generation: int | None = None
    path: str = ""


@dataclass(frozen=True)
class RecoveryReference:
    kind: str
    value: str
    resolved: bool = False


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    pgid: int
    start_ticks: int
    boot_id: str
    root_dev: int
    root_ino: int


@dataclass(frozen=True)
class OperationSpec:
    kind: str
    resources: tuple[ResourceReference, ...]
    actor_id: int | None = None
    origin: Literal["task", "cron", "request", "system"] = "request"
    name: str = ""
    operation_id: str = field(default_factory=lambda: uuid4().hex)
    legacy_id: str | None = None
    running_intent: bool | None = None
    configuration_version: str | None = None


@dataclass(frozen=True)
class OperationRecord:
    operation_id: str
    kind: str
    resources: tuple[ResourceReference, ...]
    actor_id: int | None
    origin: str
    name: str
    legacy_id: str | None
    running_intent: bool | None
    configuration_version: str | None
    state: OperationState
    phase: str
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None
    data_changed: bool
    writers_stopped: bool
    ownership_known: bool
    processes: tuple[ProcessIdentity, ...]
    recovery_refs: tuple[RecoveryReference, ...]
    failure_code: str | None
    blocked_reason: str | None
    cache_degraded: bool
    resolved_by: int | None
    resolved_at: datetime | None


@dataclass(frozen=True)
class JournalLimits:
    max_records: int = 10_000
    terminal_max_age: timedelta = timedelta(days=30)
    max_resources: int = 64
    max_recovery_refs: int = 32
    max_processes: int = 32


@dataclass(frozen=True)
class RecoveryBlock:
    operation_id: str
    resource: ResourceReference
    reason: str


@dataclass(frozen=True)
class RecoveryReport:
    interrupted_ids: tuple[str, ...] = ()
    blocks: tuple[RecoveryBlock, ...] = ()
    degraded_resources: tuple[ResourceReference, ...] = ()
