"""SnapshotService: the app-facing snapshot API.

Combines the restic client, ignore-path resolution, and restore planning.
Dynamic config is read at the point of behavior, so ignore changes apply
to the next operation without restarts. At restore time the effective
ignore set is the union of current config and the excludes recorded in the
snapshot being restored, so snapshots taken under an older ignore config
stay protected as well.
"""

import errno
import stat
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import aclosing
from pathlib import Path

import aiofiles.os as aioos
from fastapi import HTTPException

from ..dynamic_config import get_config
from ..errors import PublicOperationError
from ..operations.context import current_execution
from ..operations.finalization import finalize
from ..runtime_resources import current_runtime
from ..utils import async_fs
from .coverage import covers
from .evidence import (
    selection_tags,
    snapshot_selection,
    snapshot_source_path,
)
from .ignores import (
    InstanceProvider,
    backup_excludes,
    is_ignored,
    resolve_all_ignores,
    resolve_server_ignores,
)
from .models import (
    ResticRestoreEvent,
    ResticSnapshot,
    ResticSnapshotWithSummary,
)
from .notes import SnapshotNotes
from .path_mapping import SnapshotPathMapping
from .planner import (
    DirStep,
    EmptyStep,
    RestorePlan,
    RestoreStep,
    build_restore_plan,
)
from .protection import SnapshotProtection
from .repository_use import RepositoryUse
from .restic import ResticClient


class SnapshotService:
    def __init__(
        self,
        client: ResticClient,
        mc_manager: InstanceProvider,
        notes: SnapshotNotes | None = None,
    ):
        self._client = client
        self._mc_manager = mc_manager
        self._notes = notes
        self.repository_use = RepositoryUse()

    async def protection(
        self,
        snapshot_id: str | None = None,
        *,
        retained: Sequence[Path] = (),
        data_paths: Sequence[Path] | None = None,
    ) -> SnapshotProtection:
        current = await self._current_ignores(data_paths)
        protection = SnapshotProtection.capture(
            current, retained, data_paths=data_paths
        )
        if snapshot_id is not None:
            return await self.with_source_protection(
                protection, await self.get_snapshot(snapshot_id)
            )
        return protection

    async def with_source_protection(
        self, protection: SnapshotProtection, source: ResticSnapshot
    ) -> SnapshotProtection:
        excluded = list(protection.excluded)
        selection = snapshot_selection(source)
        if selection is not None:
            excluded.extend(selection.excluded)
            source_roots = {Path(value) for value in source.paths}
            selected_roots = {
                parent
                for item in protection.mappings
                for parent in (item.logical, *item.logical.parents)
                if parent in source_roots
            }
            for root in selected_roots:
                if await async_fs.resolve(root) != root:
                    raise HTTPException(
                        status_code=409,
                        detail="源快照对应的链接目标已变化，请重新选择范围",
                    )
        if not protection.mappings:
            excluded.extend(Path(path) for path in source.excludes)
        for mapping in protection.mappings:
            source_root = snapshot_source_path(
                source, mapping.logical, mapping.execution
            )
            if source_root != mapping.execution:
                raise HTTPException(
                    status_code=409, detail="源快照对应的链接目标已变化，请重新选择范围"
                )
            for value in source.excludes:
                path = Path(value)
                if source_root.is_relative_to(path):
                    excluded.append(mapping.logical)
                elif path.is_relative_to(source_root):
                    excluded.append(mapping.logical / path.relative_to(source_root))
        return SnapshotProtection.capture(
            protection.current,
            excluded,
            data_paths=protection.data_paths,
            mappings=protection.mappings,
        )

    async def _bind_paths(
        self, paths: Sequence[Path], protection: SnapshotProtection
    ) -> SnapshotProtection:
        mappings = {item.logical: item for item in protection.mappings}
        for path in paths:
            actual = await async_fs.resolve(path)
            existing = protection.has_mapping(path)
            expected = protection.execution_path(path) if existing else actual
            if actual != expected:
                raise HTTPException(
                    status_code=409, detail="目标路径或链接已变化，请重新确认操作"
                )
            mappings[path] = SnapshotPathMapping(path, actual)
        return protection.with_mappings(tuple(mappings.values()))

    @staticmethod
    def _execution_excludes(
        path: Path, protection: SnapshotProtection
    ) -> tuple[Path, ...]:
        execution = protection.execution_path(path)
        return tuple(
            sorted(
                {
                    execution / ignored.relative_to(path)
                    for ignored in protection.excluded
                    if ignored.is_relative_to(path)
                }
            )
        )

    @staticmethod
    def source_covers(
        source: ResticSnapshot, path: Path, protection: SnapshotProtection
    ) -> bool:
        execution = protection.execution_path(path)
        source_path = snapshot_source_path(source, path, execution)
        return protection.permits(path) and covers(
            source_path,
            [Path(value) for value in source.paths],
            [Path(value) for value in source.excludes],
        )

    async def revalidate_protection(self, protection: SnapshotProtection) -> None:
        protection.require_current(await self._current_ignores(protection.data_paths))

    async def _current_ignores(
        self, data_paths: Sequence[Path] | None = None
    ) -> list[Path]:
        if data_paths is not None:
            ignored: list[Path] = []
            for data_path in data_paths:
                ignored.extend(
                    await resolve_server_ignores(
                        data_path, get_config().snapshots.ignored_paths
                    )
                )
            return ignored
        return await resolve_all_ignores(
            self._mc_manager, get_config().snapshots.ignored_paths
        )

    async def remove_absent_paths(
        self,
        snapshot_id: str,
        paths: Sequence[Path],
        *,
        protection: SnapshotProtection | None = None,
    ) -> list[Path]:
        """Restore recorded absence without deleting configured ignored descendants."""
        protection = await self._bind_paths(
            paths, protection or await self.protection()
        )
        protection = await self.with_source_protection(
            protection, await self.get_snapshot(snapshot_id)
        )
        await self.revalidate_protection(protection)
        removed: list[Path] = []

        async def remove(path: Path, ignored: tuple[Path, ...]) -> None:
            if is_ignored(path, ignored) or not await async_fs.lexists(path):
                return
            if await aioos.path.islink(path) or not await aioos.path.isdir(path):
                await aioos.remove(path)
                removed.append(path)
                return
            for child in await async_fs.iterdir(path):
                await remove(child, ignored)
            try:
                await aioos.rmdir(path)
                removed.append(path)
            except OSError as exc:
                if exc.errno != errno.ENOTEMPTY:
                    raise

        async def apply() -> None:
            for path in paths:
                if protection.permits(path):
                    await remove(
                        protection.execution_path(path),
                        self._execution_excludes(path, protection),
                    )

        await finalize(apply())
        return removed

    async def absent_targets(
        self,
        snapshot_id: str,
        paths: Sequence[Path],
        *,
        protection: SnapshotProtection | None = None,
    ) -> tuple[Path, ...]:
        protection = await self._bind_paths(
            paths, protection or await self.protection()
        )
        by_parent: dict[Path, list[Path]] = {}
        for path in paths:
            by_parent.setdefault(protection.execution_path(path).parent, []).append(
                path
            )
        absent: list[Path] = []
        for parent, targets in by_parent.items():
            nodes = await self._client.ls(snapshot_id, parent)
            absent.extend(
                path for path in targets if protection.execution_path(path) not in nodes
            )
        return tuple(absent)

    async def create_snapshot(
        self,
        paths: Sequence[Path],
        *,
        protection: SnapshotProtection | None = None,
        tags: Sequence[str] = (),
    ) -> ResticSnapshotWithSummary:
        """Snapshot the given absolute paths, excluding configured ignores.

        Raises ``TargetIgnoredError`` when a requested path itself lies
        under an ignored path — such a snapshot would be empty by definition.
        """
        with self.repository_use.retain():
            protection = await self._bind_paths(
                paths, protection or await self.protection()
            )
            await self.revalidate_protection(protection)
            protection.require_targets(paths)
            mappings = tuple(
                SnapshotPathMapping(path, protection.execution_path(path))
                for path in paths
            )
            candidates = {
                path
                for item in mappings
                for path in self._execution_excludes(item.logical, protection)
            }
            excluded = []
            for candidate in candidates:
                views = [
                    item
                    for item in mappings
                    if candidate.is_relative_to(item.execution)
                ]
                if views and all(
                    not protection.permits(item.logical_path(candidate))
                    for item in views
                ):
                    nested = [
                        item
                        for item in mappings
                        if item.execution != candidate
                        and item.execution.is_relative_to(candidate)
                    ]
                    if any(protection.permits(item.logical) for item in nested):
                        raise HTTPException(
                            status_code=400,
                            detail="多个链接范围的排除规则重叠，请分别创建快照",
                        )
                    excluded.append(candidate)
            logical_excluded = [
                path
                for path in protection.excluded
                if any(path.is_relative_to(item.logical) for item in mappings)
            ]
            return await self._client.backup(
                sorted({item.execution for item in mappings}),
                backup_excludes([item.execution for item in mappings], excluded),
                tags=[*tags, *selection_tags(mappings, logical_excluded)],
            )

    async def build_plan(
        self,
        snapshot_id: str,
        targets: Sequence[Path],
        *,
        protection: SnapshotProtection | None = None,
    ) -> RestorePlan:
        protection = await self._bind_paths(
            targets, protection or await self.protection()
        )
        protection = await self.with_source_protection(
            protection, await self.get_snapshot(snapshot_id)
        )
        await self.revalidate_protection(protection)
        protection.require_targets(targets)
        groups: dict[tuple[Path, ...], list[SnapshotPathMapping]] = {}
        for path in targets:
            mapping = SnapshotPathMapping(path, protection.execution_path(path))
            groups.setdefault(self._execution_excludes(path, protection), []).append(
                mapping
            )
        steps: list[RestoreStep] = []
        step_mappings = []
        for excluded, mappings in groups.items():
            executions = sorted({item.execution for item in mappings})
            execution_set = set(executions)
            executions = [
                path
                for path in executions
                if not any(parent in execution_set for parent in path.parents)
            ]
            plan = await build_restore_plan(
                self._client, snapshot_id, executions, excluded
            )
            steps.extend(plan.steps)
            step_mappings.extend([tuple(mappings)] * len(plan.steps))
        return RestorePlan(snapshot_id, tuple(steps), tuple(step_mappings))

    async def restore(
        self,
        snapshot_id: str,
        targets: Sequence[Path],
        *,
        dry_run: bool = False,
        protection: SnapshotProtection | None = None,
    ) -> AsyncGenerator[ResticRestoreEvent]:
        """In-place restore with ``--delete``, ignored paths protected.

        Yields normalized events: ``status`` percents rescaled across plan
        steps, ``file`` events passed through, and one aggregated ``summary``
        at the end.
        """
        if not targets:
            return
        with self.repository_use.retain((snapshot_id,)):
            plan = await self.build_plan(snapshot_id, targets, protection=protection)
            async with aclosing(
                self._run_plan(
                    plan,
                    target_for=lambda step: step.source_dir,
                    delete=True,
                    dry_run=dry_run,
                )
            ) as events:
                async for event in events:
                    yield event

    async def stage(
        self,
        snapshot_id: str,
        targets: Sequence[Path],
        stage_root: Path,
        *,
        protection: SnapshotProtection | None = None,
    ) -> AsyncGenerator[ResticRestoreEvent]:
        """Restore targets under ``stage_root``, mirroring absolute paths.

        No ``--delete``: staging directories start empty. Use
        ``stage_destination`` to locate staged files afterwards.
        """
        with self.repository_use.retain((snapshot_id,)):
            plan = await self.build_plan(snapshot_id, targets, protection=protection)
            async with aclosing(
                self._run_plan(
                    plan,
                    target_for=lambda step: RestorePlan.stage_target(stage_root, step),
                    delete=False,
                    dry_run=False,
                )
            ) as events:
                async for event in events:
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
    ) -> AsyncGenerator[ResticRestoreEvent]:
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
            async with aclosing(
                self._restore_step(
                    plan.snapshot_id,
                    step,
                    target_dir=target_for(step),
                    delete=delete,
                    dry_run=dry_run,
                )
            ) as events:
                async for event in events:
                    if event.kind == "status":
                        if event.percent_done is not None:
                            event.percent_done = (
                                index + event.percent_done
                            ) / total_steps
                        yield event
                    elif event.kind == "file":
                        if event.item and plan.mappings:
                            item = Path(event.item)
                            matching = [
                                mapping
                                for mapping in plan.mappings[index]
                                if item.is_relative_to(mapping.execution)
                            ]
                            if matching:
                                event.item = str(
                                    max(
                                        matching,
                                        key=lambda mapping: len(
                                            mapping.execution.parts
                                        ),
                                    ).logical_path(item)
                                )
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
    ) -> AsyncGenerator[ResticRestoreEvent]:
        if isinstance(step, EmptyStep):
            if delete:
                return self._restore_empty_step(step, dry_run=dry_run)
            step = step.original
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

    async def _restore_empty_step(
        self,
        step: EmptyStep,
        *,
        dry_run: bool,
    ) -> AsyncGenerator[ResticRestoreEvent]:
        roots = [
            instance.get_data_path().parent
            for instance in await self._mc_manager.get_all_instances()
        ]
        servers_root = getattr(self._mc_manager, "servers_path", None)
        if isinstance(servers_root, Path):
            roots.append(servers_root)
        containing = [root for root in roots if step.source_dir.is_relative_to(root)]
        if not containing:
            raise PublicOperationError("空目录恢复目标不属于已登记的服务器目录")
        owner = max(containing, key=lambda path: len(path.parts))
        scope = await async_fs.resolve_inside(owner, step.source_dir)
        removals: list[tuple[Path, bool]] = []

        async def plan(path: Path, *, preserve: bool = False) -> bool:
            try:
                info = await aioos.stat(path, follow_symlinks=False)
            except FileNotFoundError:
                return False
            if is_ignored(path, step.ignored):
                return True
            await async_fs.resolve_inside(scope, path)
            directory = stat.S_ISDIR(info.st_mode)
            retained = preserve
            if directory:
                for child in sorted(await async_fs.iterdir(path)):
                    retained = await plan(child) or retained
            if not retained:
                removals.append((path, directory))
            return retained

        if isinstance(step.original, DirStep):
            await plan(step.source_dir, preserve=True)
        else:
            for name in step.original.includes:
                await plan(step.source_dir / name.removeprefix("/"))

        async def remove() -> list[Path]:
            removed: list[Path] = []
            for path, directory in removals:
                await async_fs.resolve_inside(scope, path)
                try:
                    if directory:
                        await aioos.rmdir(path)
                    else:
                        await aioos.unlink(path)
                except FileNotFoundError:
                    continue
                removed.append(path)
            return removed

        removed = (
            [path for path, _ in removals] if dry_run else await finalize(remove())
        )
        for path in removed:
            yield ResticRestoreEvent(
                kind="file", action="deleted", item=str(path), size=0
            )
        yield ResticRestoreEvent(kind="summary", files_deleted=len(removed))

    async def get_snapshot(self, snapshot_id: str) -> ResticSnapshot:
        snapshot = await self._client.get_snapshot(snapshot_id)
        await self._project_notes([snapshot])
        return snapshot

    async def save_note(self, snapshot_id: str, note: str) -> ResticSnapshot:
        if self._notes is None:
            raise HTTPException(status_code=503, detail="快照备注服务不可用")
        with self.repository_use.retain([snapshot_id]):
            snapshot = await self._client.get_snapshot(snapshot_id)
            await self._notes.save(
                await self._client.repository_id(), snapshot.id, note
            )
            snapshot.note = note
            return snapshot

    async def _project_notes(self, snapshots: list[ResticSnapshot]) -> None:
        if self._notes is None or not snapshots:
            return
        notes = await self._notes.read(
            await self._client.repository_id(), [snapshot.id for snapshot in snapshots]
        )
        for snapshot in snapshots:
            snapshot.note = notes.get(snapshot.id, "")

    async def list_snapshots(
        self, path_filter: Path | None = None
    ) -> list[ResticSnapshot]:
        """All snapshots; with ``path_filter`` keep those whose recorded paths
        cover it and whose recorded excludes don't disqualify it."""
        snapshots = await self._client.list_snapshots()
        if path_filter is None:
            await self._project_notes(snapshots)
            return snapshots

        protection = await self._bind_paths([path_filter], await self.protection())
        filtered: list[ResticSnapshot] = []
        for snapshot in snapshots:
            try:
                protected = await self.with_source_protection(protection, snapshot)
            except HTTPException as error:
                if error.status_code == 409:
                    continue
                raise
            if self.source_covers(snapshot, path_filter, protected):
                filtered.append(snapshot)
        await self._project_notes(filtered)
        return filtered

    async def find_snapshots_covering(
        self, paths: Sequence[Path]
    ) -> list[ResticSnapshot]:
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
        protection = await self._bind_paths(paths, await self.protection())

        matching: list[ResticSnapshot] = []
        for snapshot in all_snapshots:
            try:
                protected = await self.with_source_protection(protection, snapshot)
            except HTTPException as error:
                if error.status_code == 409:
                    continue
                raise
            if all(self.source_covers(snapshot, target, protected) for target in paths):
                matching.append(snapshot)
        matching.sort(key=lambda s: s.time, reverse=True)
        await self._project_notes(matching)
        return matching

    @staticmethod
    async def _resolved_coverage_paths(
        snapshot: ResticSnapshot,
    ) -> tuple[list[Path], list[Path]]:
        paths = [Path(p) for p in snapshot.paths]
        excludes = [Path(e) for e in snapshot.excludes]
        return paths, excludes

    async def forget_id(
        self, snapshot_id: str, prune: bool = True, *, reservation: object | None = None
    ) -> str:
        with self.repository_use.maintain(reservation):
            await self._require_stopped_repository_writers()
            return await self._client.forget_id(snapshot_id, prune=prune)

    async def forget(
        self,
        keep_last: int | None = None,
        keep_hourly: int | None = None,
        keep_daily: int | None = None,
        keep_weekly: int | None = None,
        keep_monthly: int | None = None,
        keep_yearly: int | None = None,
        keep_tag: list[str] | None = None,
        keep_within: str | None = None,
        prune: bool = True,
    ) -> str:
        with self.repository_use.maintain():
            await self._require_stopped_repository_writers()
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

    async def unlock(self, *, reservation: object | None = None) -> str:
        with self.repository_use.maintain(reservation):
            await self._require_stopped_repository_writers()
            return await self._client.unlock()

    async def _require_stopped_repository_writers(self) -> None:
        journal = current_runtime().journal
        if journal is not None:
            own = current_execution()
            for record in await journal.unsettled():
                if own is not None and record.operation_id == own.operation_id:
                    continue
                if not record.writers_stopped and (
                    record.kind.startswith("snapshot_")
                    or record.kind in {"world_restore", "cron_backup"}
                    or any(
                        ref.kind in {"safety_snapshot", "source_snapshot"}
                        for ref in record.recovery_refs
                    )
                ):
                    raise HTTPException(
                        status_code=423, detail="仓库写入尚未确认结束，请先核对操作历史"
                    )


def _accumulate_summary(total: ResticRestoreEvent, part: ResticRestoreEvent) -> None:
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
