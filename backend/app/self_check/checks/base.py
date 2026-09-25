"""Shared primitives for built-in self-check implementations."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.servers.models import Server

from ...errors import log_safe_error, public_error_message
from ...runtime_resources import current_runtime
from ...servers.crud import get_active_servers
from ...snapshots import ResticSnapshot
from ...snapshots.coverage import covers
from ...utils import async_fs
from ..types import SelfCheckFindingResult

if TYPE_CHECKING:
    from ...config import Settings
    from ...dns.manager import SimpleDNSManager
    from ...dynamic_config import ConfigProxy
    from ...log_monitor.monitor import LogMonitor
    from ...minecraft.manager import DockerMCManager
    from ...snapshots.service import SnapshotService
    from ...world.locks import ServerOperationLock


@dataclass
class SelfCheckDependencies:
    settings: "Settings"
    configuration: "ConfigProxy"
    minecraft: "DockerMCManager"
    snapshots: "SnapshotService | None"
    connectivity: "SimpleDNSManager"
    logs: "LogMonitor"
    locks: "ServerOperationLock"


def get_self_check_dependencies() -> SelfCheckDependencies:
    return current_runtime().resource("self_check_dependencies")


@dataclass(frozen=True)
class CheckDefinition:
    check_id: str
    category: str
    title: str
    description: str
    function: Callable[["SelfCheckContext"], Awaitable[list[SelfCheckFindingResult]]]


class SelfCheckContext:
    def __init__(
        self, db: AsyncSession, self_check_config: Any | None = None, *,
        dependencies: SelfCheckDependencies | None = None,
    ) -> None:
        self.db = db
        self.dependencies = dependencies or get_self_check_dependencies()
        self.config = self_check_config or self.dependencies.configuration.self_check
        self.now = datetime.now(UTC)
        self._active_servers: list[Server] | None = None
        self._filesystem_servers: set[str] | None = None
        self._snapshots: list[ResticSnapshot] | None = None
        self._snapshot_error: str | None = None
        self._resolved_coverage: dict[str, tuple[list[Path], list[Path]]] = {}

    async def active_servers(self) -> list[Server]:
        if self._active_servers is None:
            self._active_servers = await get_active_servers(self.db)
        return self._active_servers

    async def filesystem_servers(self) -> set[str]:
        if self._filesystem_servers is None:
            self._filesystem_servers = set(
                await self.dependencies.minecraft.get_all_server_names()
            )
        return self._filesystem_servers

    async def snapshots(self) -> tuple[list[ResticSnapshot] | None, str | None]:
        if not self.dependencies.snapshots:
            return None, None
        if self._snapshots is None and self._snapshot_error is None:
            try:
                self._snapshots = await self.dependencies.snapshots.list_snapshots()
            except Exception as exc:  # noqa: BLE001 - optional repository failure must not abort unrelated checks
                log_safe_error(exc, "Cannot list snapshots for self-check")
                self._snapshot_error = public_error_message(exc)
        return self._snapshots, self._snapshot_error

    async def snapshots_covering(self, target: Path) -> list[ResticSnapshot]:
        snapshots, error = await self.snapshots()
        if error or snapshots is None:
            return []

        resolved_target = await async_fs.resolve(target)
        matches: list[ResticSnapshot] = []
        for snapshot in snapshots:
            if snapshot.id not in self._resolved_coverage:
                self._resolved_coverage[snapshot.id] = (
                    [await async_fs.resolve(Path(p)) for p in snapshot.paths],
                    [await async_fs.resolve(Path(e)) for e in snapshot.excludes],
                )
            paths, excludes = self._resolved_coverage[snapshot.id]
            if covers(resolved_target, paths, excludes):
                matches.append(snapshot)

        matches.sort(key=lambda item: item.time, reverse=True)
        return matches


def finding(
    *,
    check_id: str,
    category: str,
    severity: str,
    status: str,
    title: str,
    message: str,
    server_id: str | None = None,
    evidence: dict | None = None,
    remediation: list[str] | None = None,
) -> SelfCheckFindingResult:
    return SelfCheckFindingResult(
        check_id=check_id,
        category=category,
        severity=severity,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        title=title,
        message=message,
        server_id=server_id,
        evidence=evidence or {},
        remediation=remediation or [],
        created_at=datetime.now(UTC),
    )


def success(definition: CheckDefinition, message: str) -> list[SelfCheckFindingResult]:
    return [
        finding(
            check_id=definition.check_id,
            category=definition.category,
            severity="success",
            status="passed",
            title=definition.title,
            message=message,
        )
    ]


def skipped(definition: CheckDefinition, message: str) -> list[SelfCheckFindingResult]:
    return [
        finding(
            check_id=definition.check_id,
            category=definition.category,
            severity="info",
            status="skipped",
            title=definition.title,
            message=message,
        )
    ]


def usage_percent(used: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return (used / total) * 100


_finding = finding
_success = success
_skipped = skipped
_usage_percent = usage_percent
