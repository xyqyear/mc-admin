"""SnapshotService: the app-facing snapshot API.

Combines the restic client, ignore-path resolution, and restore planning.
Dynamic config is read at the point of behavior, so ignore changes apply
to the next operation without restarts. At restore time the effective
ignore set is the union of current config and the excludes recorded in the
snapshot being restored, so snapshots taken under an older ignore config
stay protected as well.
"""

from collections.abc import AsyncGenerator, Callable, Sequence
from pathlib import Path
from typing import List, Optional

from ..dynamic_config import config
from ..utils import async_fs
from .coverage import covers
from .ignores import (
    InstanceProvider,
    backup_excludes,
    is_ignored,
    resolve_all_ignores,
)
from .models import (
    ResticRestoreEvent,
    ResticSnapshot,
    ResticSnapshotWithSummary,
)
from .planner import (
    DirStep,
    RestorePlan,
    RestoreStep,
    TargetIgnoredError,
    build_restore_plan,
)
from .restic import ResticClient


class SnapshotService:
    def __init__(self, client: ResticClient, mc_manager: InstanceProvider):
        self._client = client
        self._mc_manager = mc_manager

    async def _current_ignores(self) -> list[Path]:
        return await resolve_all_ignores(
            self._mc_manager, config.snapshots.ignored_paths
        )

    async def create_snapshot(
        self, paths: Sequence[Path]
    ) -> ResticSnapshotWithSummary:
        """Snapshot the given absolute paths, excluding configured ignores.

        Raises ``TargetIgnoredError`` when a requested path itself lies
        under an ignored path — such a snapshot would be empty by definition.
        """
        ignored = await self._current_ignores()
        for path in paths:
            if is_ignored(path, ignored):
                raise TargetIgnoredError(
                    f"路径在忽略列表中，无法创建快照: {path}"
                )
        return await self._client.backup(paths, backup_excludes(paths, ignored))

    async def build_plan(
        self, snapshot_id: str, targets: Sequence[Path]
    ) -> RestorePlan:
        snapshot = await self._client.get_snapshot(snapshot_id)
        ignored = await self._current_ignores()
        for exclude in snapshot.excludes:
            ignored.append(await async_fs.resolve(Path(exclude)))
        return await build_restore_plan(self._client, snapshot_id, targets, ignored)

    async def restore(
        self,
        snapshot_id: str,
        targets: Sequence[Path],
        *,
        dry_run: bool = False,
    ) -> AsyncGenerator[ResticRestoreEvent, None]:
        """In-place restore with ``--delete``, ignored paths protected.

        Yields normalized events: ``status`` percents rescaled across plan
        steps, ``file`` events passed through, and one aggregated ``summary``
        at the end.
        """
        plan = await self.build_plan(snapshot_id, targets)
        async for event in self._run_plan(
            plan, target_for=lambda step: step.source_dir, delete=True, dry_run=dry_run
        ):
            yield event

    async def preview(
        self, snapshot_id: str, targets: Sequence[Path]
    ) -> List[ResticRestoreEvent]:
        """Dry-run restore returning meaningful per-file actions.

        Zero-size ``restored`` items (directory entries restic reports but
        doesn't really restore) and ``unchanged`` items are dropped.
        """
        actions: List[ResticRestoreEvent] = []
        async for event in self.restore(snapshot_id, targets, dry_run=True):
            if event.kind != "file":
                continue
            if event.action == "unchanged":
                continue
            if event.action == "restored" and not event.size:
                continue
            actions.append(event)
        return actions

    async def stage(
        self,
        snapshot_id: str,
        targets: Sequence[Path],
        stage_root: Path,
    ) -> AsyncGenerator[ResticRestoreEvent, None]:
        """Restore targets under ``stage_root``, mirroring absolute paths.

        No ``--delete``: staging directories start empty. Use
        ``stage_destination`` to locate staged files afterwards.
        """
        plan = await self.build_plan(snapshot_id, targets)
        async for event in self._run_plan(
            plan,
            target_for=lambda step: RestorePlan.stage_target(stage_root, step),
            delete=False,
            dry_run=False,
        ):
            yield event

    @staticmethod
    def stage_destination(stage_root: Path, live_path: Path) -> Path:
        """Where ``live_path`` lands under ``stage_root`` after ``stage``."""
        if not live_path.is_absolute():
            raise ValueError("live_path must be absolute")
        return stage_root / live_path.relative_to("/")

    async def _run_plan(
        self,
        plan: RestorePlan,
        *,
        target_for: Callable[[RestoreStep], Path],
        delete: bool,
        dry_run: bool,
    ) -> AsyncGenerator[ResticRestoreEvent, None]:
        total_steps = len(plan.steps)
        summary = ResticRestoreEvent(
            kind="summary",
            total_files=0,
            files_restored=0,
            files_skipped=0,
            files_deleted=0,
            total_bytes=0,
            bytes_restored=0,
            bytes_skipped=0,
        )
        for index, step in enumerate(plan.steps):
            async for event in self._restore_step(
                plan.snapshot_id,
                step,
                target_dir=target_for(step),
                delete=delete,
                dry_run=dry_run,
            ):
                if event.kind == "status":
                    if event.percent_done is not None:
                        event.percent_done = (
                            index + event.percent_done
                        ) / total_steps
                    yield event
                elif event.kind == "file":
                    yield event
                else:
                    _accumulate_summary(summary, event)
        yield summary

    def _restore_step(
        self,
        snapshot_id: str,
        step: RestoreStep,
        *,
        target_dir: Path,
        delete: bool,
        dry_run: bool,
    ) -> AsyncGenerator[ResticRestoreEvent, None]:
        if isinstance(step, DirStep):
            return self._client.restore(
                snapshot_id,
                source_dir=step.source_dir,
                target_dir=target_dir,
                excludes=step.excludes,
                delete=delete,
                dry_run=dry_run,
            )
        return self._client.restore(
            snapshot_id,
            source_dir=step.source_dir,
            target_dir=target_dir,
            includes=step.includes,
            delete=delete,
            dry_run=dry_run,
        )

    async def get_snapshot(self, snapshot_id: str) -> ResticSnapshot:
        return await self._client.get_snapshot(snapshot_id)

    async def list_snapshots(
        self, path_filter: Optional[Path] = None
    ) -> List[ResticSnapshot]:
        """All snapshots; with ``path_filter`` keep those whose recorded paths
        cover it and whose recorded excludes don't disqualify it."""
        snapshots = await self._client.list_snapshots()
        if path_filter is None:
            return snapshots

        resolved_filter = await async_fs.resolve(path_filter)
        filtered: List[ResticSnapshot] = []
        for snapshot in snapshots:
            paths, excludes = await self._resolved_coverage_paths(snapshot)
            if covers(resolved_filter, paths, excludes):
                filtered.append(snapshot)
        return filtered

    async def find_snapshots_covering(
        self, paths: Sequence[Path]
    ) -> List[ResticSnapshot]:
        """Snapshots that cover *every* input path; newest-first.

        Coverage is exclude-aware: a snapshot whose recorded excludes contain
        one of the targets does not qualify, even if its recorded paths do.
        """
        if not paths:
            raise ValueError("At least one path must be provided")
        for path in paths:
            if not path.is_absolute():
                raise ValueError("Paths must be absolute")

        all_snapshots = await self._client.list_snapshots()
        resolved_targets = [await async_fs.resolve(p) for p in paths]

        matching: List[ResticSnapshot] = []
        for snapshot in all_snapshots:
            snap_paths, snap_excludes = await self._resolved_coverage_paths(snapshot)
            if all(
                covers(target, snap_paths, snap_excludes)
                for target in resolved_targets
            ):
                matching.append(snapshot)
        matching.sort(key=lambda s: s.time, reverse=True)
        return matching

    @staticmethod
    async def _resolved_coverage_paths(
        snapshot: ResticSnapshot,
    ) -> tuple[list[Path], list[Path]]:
        paths = [await async_fs.resolve(Path(p)) for p in snapshot.paths]
        excludes = [await async_fs.resolve(Path(e)) for e in snapshot.excludes]
        return paths, excludes

    async def forget_id(self, snapshot_id: str, prune: bool = True) -> str:
        return await self._client.forget_id(snapshot_id, prune=prune)

    async def forget(
        self,
        keep_last: Optional[int] = None,
        keep_hourly: Optional[int] = None,
        keep_daily: Optional[int] = None,
        keep_weekly: Optional[int] = None,
        keep_monthly: Optional[int] = None,
        keep_yearly: Optional[int] = None,
        keep_tag: Optional[List[str]] = None,
        keep_within: Optional[str] = None,
        prune: bool = True,
    ) -> str:
        return await self._client.forget(
            keep_last=keep_last,
            keep_hourly=keep_hourly,
            keep_daily=keep_daily,
            keep_weekly=keep_weekly,
            keep_monthly=keep_monthly,
            keep_yearly=keep_yearly,
            keep_tag=keep_tag,
            keep_within=keep_within,
            prune=prune,
        )

    async def list_locks(self) -> str:
        return await self._client.list_locks()

    async def unlock(self) -> str:
        return await self._client.unlock()


def _accumulate_summary(
    total: ResticRestoreEvent, part: ResticRestoreEvent
) -> None:
    for field in (
        "total_files",
        "files_restored",
        "files_skipped",
        "files_deleted",
        "total_bytes",
        "bytes_restored",
        "bytes_skipped",
    ):
        value = getattr(part, field)
        if value is not None:
            setattr(total, field, (getattr(total, field) or 0) + value)
