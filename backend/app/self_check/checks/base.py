"""Shared primitives for built-in self-check implementations."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from ...dynamic_config import config
from ...minecraft import docker_mc_manager
from ...models import Server
from ...servers.crud import get_active_servers
from ...snapshots import ResticSnapshot, restic_manager
from ...utils import async_fs
from ..types import SelfCheckFindingResult


@dataclass(frozen=True)
class CheckDefinition:
    check_id: str
    category: str
    title: str
    description: str
    function: Callable[["SelfCheckContext"], Awaitable[list[SelfCheckFindingResult]]]


class SelfCheckContext:
    def __init__(self, db: AsyncSession, self_check_config: Any | None = None) -> None:
        self.db = db
        self.config = self_check_config or config.self_check
        self.now = datetime.now(timezone.utc)
        self._active_servers: list[Server] | None = None
        self._filesystem_servers: set[str] | None = None
        self._snapshots: list[ResticSnapshot] | None = None
        self._snapshot_error: str | None = None
        self._resolved_snapshot_paths: dict[str, list[Path]] = {}

    async def active_servers(self) -> list[Server]:
        if self._active_servers is None:
            self._active_servers = await get_active_servers(self.db)
        return self._active_servers

    async def filesystem_servers(self) -> set[str]:
        if self._filesystem_servers is None:
            self._filesystem_servers = set(
                await docker_mc_manager.get_all_server_names()
            )
        return self._filesystem_servers

    async def snapshots(self) -> tuple[list[ResticSnapshot] | None, str | None]:
        if restic_manager is None:
            return None, None
        if self._snapshots is None and self._snapshot_error is None:
            try:
                self._snapshots = await restic_manager.list_snapshots()
            except Exception as exc:
                self._snapshot_error = str(exc)
        return self._snapshots, self._snapshot_error

    async def snapshots_covering(self, target: Path) -> list[ResticSnapshot]:
        snapshots, error = await self.snapshots()
        if error or snapshots is None:
            return []

        resolved_target = await async_fs.resolve(target)
        matches: list[ResticSnapshot] = []
        for snapshot in snapshots:
            if snapshot.id not in self._resolved_snapshot_paths:
                self._resolved_snapshot_paths[snapshot.id] = [
                    await async_fs.resolve(Path(snapshot_path))
                    for snapshot_path in snapshot.paths
                ]
            for snapshot_path in self._resolved_snapshot_paths[snapshot.id]:
                try:
                    resolved_target.relative_to(snapshot_path)
                    matches.append(snapshot)
                    break
                except ValueError:
                    continue

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
        created_at=datetime.now(timezone.utc),
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
