"""Per-server maintenance ownership shared by snapshots, world writes and startup."""

from collections.abc import AsyncGenerator, Iterator, Sequence
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from ..operations.coordinator import (
    ConflictPolicy,
    OperationCoordinator,
    ResourceClaim,
    ResourceKind,
    ResourceLease,
)
from ..runtime_resources import current_runtime

GLOBAL_LOCK_KEY = "__global__"


class ServerOperationKind(str, Enum):
    BACKUP = "backup"
    RESTORE = "restore"
    PRUNE = "prune"
    START = "start"
    REBUILD = "rebuild"


@dataclass
class LockHolder:
    kind: ServerOperationKind
    started_at: datetime
    user_id: int | None
    description: str
    restoration_id: str | None = None


class ServerOperationLock:
    """Per-server async mutex.

    Acquired via the ``acquire`` async context manager, which guarantees
    release via ``try/finally`` even on exception. Map render queues
    intentionally do NOT use this lock. Backup, restore, prune and startup
    share ownership so stopped-world writes cannot overlap server startup.
    """

    def __init__(self, coordinator: OperationCoordinator | None = None) -> None:
        self._coordinator = coordinator if coordinator is not None else OperationCoordinator()
        self._holders: dict[str, LockHolder] = {}

    @staticmethod
    def _claims(server_ids: list[str]) -> list[ResourceClaim]:
        return [ResourceClaim(ResourceKind.MAINTENANCE, server_id) for server_id in server_ids]

    @contextmanager
    def reuse(self, lease: ResourceLease, server_ids: list[str], *, claims: Sequence[ResourceClaim] = ()) -> Iterator[ResourceLease]:
        with self._coordinator.reuse(lease, [*self._claims(server_ids), *claims]):
            yield lease

    @asynccontextmanager
    async def lease(
        self, server_ids: list[str], holder: LockHolder, *,
        claims: Sequence[ResourceClaim] = (), policy: ConflictPolicy = ConflictPolicy.WAIT,
        parent: ResourceLease | None = None,
    ) -> AsyncGenerator[ResourceLease | None]:
        async with self._coordinator.acquire([*self._claims(server_ids), *claims], policy=policy, parent=parent) as lease:
            if lease is None:
                yield None
                return
            previous = {server_id: self._holders.get(server_id) for server_id in server_ids}
            try:
                for server_id in server_ids:
                    self._holders.setdefault(server_id, holder)
                yield lease
            finally:
                for server_id, original in previous.items():
                    if original is None:
                        self._holders.pop(server_id, None)
                    else:
                        self._holders[server_id] = original

    @asynccontextmanager
    async def acquire(
        self, server_id: str, holder: LockHolder
    ) -> AsyncGenerator[ResourceLease]:
        async with self.lease([server_id], holder) as lease:
            assert lease is not None
            yield lease

    @asynccontextmanager
    async def try_acquire(
        self, server_id: str, holder: LockHolder, *, allocate_ports: bool = False,
    ) -> AsyncGenerator[bool]:
        async with self.try_acquire_servers([server_id], holder, allocate_ports=allocate_ports) as acquired:
            yield acquired

    def is_locked(self, server_id: str) -> bool:
        return (
            self._coordinator.admission.is_frozen(server_id)
            or self._coordinator.admission.recovery_reason(server_id) is not None
            or self._coordinator.is_occupied(self._claims([server_id])[0])
        )

    @asynccontextmanager
    async def try_acquire_servers(
        self, server_ids: list[str], holder: LockHolder, *, allocate_ports: bool = False,
    ) -> AsyncGenerator[bool]:
        claims = []
        if allocate_ports:
            claims.append(ResourceClaim(ResourceKind.PORT_ALLOCATION))
        async with self.lease(
            server_ids, holder, claims=claims, policy=ConflictPolicy.SKIP
        ) as lease:
            if lease is None:
                yield False
                return
            yield True

    def get_holder(self, server_id: str) -> LockHolder | None:
        return self._holders.get(server_id)

    def get_holders(self) -> dict[str, LockHolder]:
        return dict(self._holders)


def get_server_operation_lock() -> ServerOperationLock:
    return current_runtime().resource('server_operation_lock')
