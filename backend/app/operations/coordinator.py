"""Atomic admission of explicitly declared operation resources."""

import asyncio
from collections.abc import AsyncGenerator, Iterator, Sequence
from contextlib import ExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass
from enum import Enum, IntEnum
from pathlib import PurePosixPath

from fastapi import HTTPException

from ..operation_admission import ServerWriteAdmission, get_server_write_admission
from ..runtime_resources import current_runtime
from .context import revalidate_targets


class ResourceKind(IntEnum):
    PORT_ALLOCATION = 0
    MAINTENANCE = 1
    FILES = 2
    MAP_CACHE = 3
    ARCHIVE = 4


class ConflictPolicy(str, Enum):
    WAIT = "wait"
    REJECT = "reject"
    SKIP = "skip"


@dataclass(frozen=True, order=True)
class ResourceClaim:
    kind: ResourceKind
    server_id: str = ""
    path: str = ""

    def __post_init__(self) -> None:
        if self.path and (PurePosixPath(self.path).is_absolute() or ".." in PurePosixPath(self.path).parts):
            raise ValueError("Operation resource paths must be confined relative paths")

    def covers(self, other: "ResourceClaim") -> bool:
        if self.kind == ResourceKind.FILES and not self.server_id and not self.path:
            return other.kind == ResourceKind.FILES
        if (self.kind, self.server_id) != (other.kind, other.server_id):
            return False
        return PurePosixPath(other.path).is_relative_to(PurePosixPath(self.path))

    def conflicts(self, other: "ResourceClaim") -> bool:
        return self.covers(other) or other.covers(self)


@dataclass(frozen=True, eq=False)
class ResourceLease:
    claims: tuple[ResourceClaim, ...]
    owner: object


class OperationCoordinator:
    def __init__(self, admission: ServerWriteAdmission | None = None) -> None:
        self.admission = admission if admission is not None else get_server_write_admission()
        self._leases: set[ResourceLease] = set()
        self._changed = asyncio.Event()

    def is_occupied(self, claim: ResourceClaim) -> bool:
        return any(claim.conflicts(held) for lease in self._leases for held in lease.claims)

    def global_files_busy(self) -> bool:
        return any(held.kind == ResourceKind.FILES and not held.server_id and not held.path for lease in self._leases for held in lease.claims)

    @asynccontextmanager
    async def delete(self, server_id: str, permit: object) -> AsyncGenerator[ResourceLease]:
        self.admission.validate_deletion(server_id, permit)
        claims = tuple(ResourceClaim(kind, server_id) for kind in (
            ResourceKind.MAINTENANCE, ResourceKind.FILES, ResourceKind.MAP_CACHE,
        ))
        if any(self.is_occupied(claim) for claim in claims):
            raise HTTPException(status_code=423, detail="服务器仍有操作未结束，请稍后重试删除")
        lease = ResourceLease(claims, permit)
        self._leases.add(lease)
        try:
            await revalidate_targets()
            yield lease
        finally:
            self._leases.remove(lease)
            changed = self._changed
            self._changed = asyncio.Event()
            changed.set()

    def _validate_parent(self, parent: ResourceLease, claims: tuple[ResourceClaim, ...]) -> None:
        if parent not in self._leases:
            raise RuntimeError("The parent operation lease is no longer active")
        if any(not any(held.covers(claim) for held in parent.claims) for claim in claims):
            raise RuntimeError("A nested operation cannot expand its parent's resource scope")

    @contextmanager
    def reuse(self, parent: ResourceLease, claims: Sequence[ResourceClaim]) -> Iterator[ResourceLease]:
        self._validate_parent(parent, tuple(sorted(set(claims))))
        yield parent

    @asynccontextmanager
    async def acquire(
        self,
        claims: Sequence[ResourceClaim],
        *,
        policy: ConflictPolicy = ConflictPolicy.WAIT,
        parent: ResourceLease | None = None,
    ) -> AsyncGenerator[ResourceLease | None]:
        ordered = tuple(sorted(set(claims)))
        if parent is not None:
            with self.reuse(parent, ordered) as lease:
                yield lease
            return
        servers = sorted({claim.server_id for claim in ordered if claim.server_id})
        archives = [claim.path for claim in ordered if claim.kind == ResourceKind.ARCHIVE]
        global_files = any(claim.kind == ResourceKind.FILES and not claim.server_id and not claim.path for claim in ordered)
        with ExitStack() as admission:
            try:
                if archives:
                    self.admission.check_archive(archives)
                admission.enter_context(self.admission.write_global() if global_files else self.admission.write(servers))
            except HTTPException:
                if policy is ConflictPolicy.SKIP:
                    yield None
                    return
                raise
            while any(self.is_occupied(claim) for claim in ordered):
                if policy is ConflictPolicy.SKIP:
                    yield None
                    return
                if policy is ConflictPolicy.REJECT:
                    raise HTTPException(status_code=423, detail="操作范围正在使用，请等待操作完成")
                changed = self._changed
                await changed.wait()
                for server_id in servers:
                    self.admission.check(server_id)
                if global_files:
                    self.admission.check("")
                if archives:
                    self.admission.check_archive(archives)
            lease = ResourceLease(ordered, object())
            self._leases.add(lease)
            try:
                await revalidate_targets()
                yield lease
            finally:
                self._leases.remove(lease)
                changed = self._changed
                self._changed = asyncio.Event()
                changed.set()


def get_operation_coordinator() -> OperationCoordinator:
    return current_runtime().resource('operation_coordinator')
