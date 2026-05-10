"""Core restic operations. Server-path resolution lives in the endpoint layer."""

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel

from ..config import settings
from ..utils import async_fs
from ..utils.exec import exec_command


class ResticSnapshot(BaseModel):
    time: datetime
    paths: List[str]
    hostname: str
    username: str
    program_version: Optional[str] = None
    id: str
    short_id: str


class ResticSnapshotSummary(BaseModel):
    backup_start: Optional[datetime] = None
    backup_end: Optional[datetime] = None
    files_new: Optional[int] = None
    files_changed: Optional[int] = None
    files_unmodified: Optional[int] = None
    dirs_new: Optional[int] = None
    dirs_changed: Optional[int] = None
    dirs_unmodified: Optional[int] = None
    data_blobs: Optional[int] = None
    tree_blobs: Optional[int] = None
    data_added: Optional[int] = None
    data_added_packed: Optional[int] = None
    total_files_processed: Optional[int] = None
    total_bytes_processed: Optional[int] = None


class ResticSnapshotWithSummary(ResticSnapshot):
    summary: Optional[ResticSnapshotSummary] = None


class ResticRestorePreviewAction(BaseModel):
    message_type: str
    action: Optional[str] = None
    item: Optional[str] = None
    size: Optional[int] = None


ResticRestoreFileAction = Literal["unchanged", "updated", "restored", "deleted"]


class ResticRestoreEvent(BaseModel):
    """One parsed line from streaming ``restic restore --json -vv``.

    Kinds: ``status`` (periodic ``percent_done`` ∈ [0, 1]),
    ``file`` (per-file action), ``summary`` (final tallies, once).

    For ``action="deleted"`` ``item`` is the target-mapped on-disk path; for
    other actions ``item`` is the snapshot's recorded absolute path.
    """

    kind: Literal["status", "file", "summary"]
    percent_done: Optional[float] = None
    total_files: Optional[int] = None
    files_restored: Optional[int] = None
    files_skipped: Optional[int] = None
    files_deleted: Optional[int] = None
    total_bytes: Optional[int] = None
    bytes_restored: Optional[int] = None
    bytes_skipped: Optional[int] = None
    action: Optional[ResticRestoreFileAction] = None
    item: Optional[str] = None
    size: Optional[int] = None


def _parse_restore_event(data: dict) -> Optional[ResticRestoreEvent]:
    """Convert one decoded JSON line into a ``ResticRestoreEvent`` (or skip)."""
    mt = data.get("message_type")
    if mt == "status":
        return ResticRestoreEvent(
            kind="status",
            percent_done=data.get("percent_done"),
            total_files=data.get("total_files"),
            files_restored=data.get("files_restored"),
            files_skipped=data.get("files_skipped"),
            total_bytes=data.get("total_bytes"),
            bytes_restored=data.get("bytes_restored"),
            bytes_skipped=data.get("bytes_skipped"),
        )
    if mt == "verbose_status":
        action = data.get("action")
        if action not in ("unchanged", "updated", "restored", "deleted"):
            return None
        return ResticRestoreEvent(
            kind="file",
            action=action,
            item=data.get("item"),
            size=data.get("size"),
        )
    if mt == "summary":
        return ResticRestoreEvent(
            kind="summary",
            total_files=data.get("total_files"),
            files_restored=data.get("files_restored"),
            files_skipped=data.get("files_skipped"),
            files_deleted=data.get("files_deleted") or 0,
            total_bytes=data.get("total_bytes"),
            bytes_restored=data.get("bytes_restored"),
            bytes_skipped=data.get("bytes_skipped"),
        )
    return None


class ResticManager:
    def __init__(self, repository_path: str, password: str | None = None):
        """``password=None`` or empty string means the repository is unprotected."""
        self.repository_path = repository_path
        self.password = password
        self.use_password = password is not None and password.strip() != ""

        self.env = {"RESTIC_REPOSITORY": repository_path}
        if self.use_password:
            self.env["RESTIC_PASSWORD"] = password

    def _add_password_args(self, args: list[str]) -> list[str]:
        if not self.use_password:
            args.append("--insecure-no-password")
        return args

    async def backup(self, paths: List[Path]) -> ResticSnapshotWithSummary:
        """Capture all given absolute paths into a single snapshot."""
        if not paths:
            raise ValueError("At least one path must be provided for restic backup")
        for path in paths:
            if not path.is_absolute():
                raise ValueError("Path must be absolute for restic backup")

        args = self._add_password_args(
            [
                "restic",
                "backup",
                *(str(p) for p in paths),
                "--exclude",
                ".mcmap",
                "--json",
            ]
        )
        result = await exec_command(*args, env=self.env)

        lines = result.strip().split("\n")
        summary_data = None
        snapshot_id = None

        for line in reversed(lines):
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            if data.get("message_type") == "summary":
                summary_data = data
                snapshot_id = data.get("snapshot_id")
                break

        if not summary_data or not snapshot_id:
            raise RuntimeError(
                "Could not parse snapshot data from restic backup output"
            )

        args = self._add_password_args(["restic", "snapshots", snapshot_id, "--json"])
        snapshots_result = await exec_command(*args, env=self.env)

        try:
            snapshots_list = json.loads(snapshots_result)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Could not parse snapshot info JSON: {e}")

        if not snapshots_list or not isinstance(snapshots_list, list):
            raise RuntimeError("Expected snapshots list from restic")

        snapshot_info = snapshots_list[0]

        summary = ResticSnapshotSummary(
            backup_start=datetime.fromisoformat(
                summary_data["backup_start"].replace("Z", "+00:00")
            ),
            backup_end=datetime.fromisoformat(
                summary_data["backup_end"].replace("Z", "+00:00")
            ),
            files_new=summary_data.get("files_new"),
            files_changed=summary_data.get("files_changed"),
            files_unmodified=summary_data.get("files_unmodified"),
            dirs_new=summary_data.get("dirs_new"),
            dirs_changed=summary_data.get("dirs_changed"),
            dirs_unmodified=summary_data.get("dirs_unmodified"),
            data_blobs=summary_data.get("data_blobs"),
            tree_blobs=summary_data.get("tree_blobs"),
            data_added=summary_data.get("data_added"),
            data_added_packed=summary_data.get("data_added_packed"),
            total_files_processed=summary_data.get("total_files_processed"),
            total_bytes_processed=summary_data.get("total_bytes_processed"),
        )

        return ResticSnapshotWithSummary(
            time=datetime.fromisoformat(snapshot_info["time"].replace("Z", "+00:00")),
            paths=snapshot_info["paths"],
            hostname=snapshot_info["hostname"],
            username=snapshot_info["username"],
            program_version=snapshot_info.get("program_version"),
            id=snapshot_info["id"],
            short_id=snapshot_info["short_id"],
            summary=summary,
        )

    async def list_snapshots(
        self, path_filter: Optional[Path] = None
    ) -> List[ResticSnapshot]:
        """Return all snapshots; with ``path_filter`` keep only those covering it."""
        args = self._add_password_args(["restic", "snapshots", "--json"])
        result = await exec_command(*args, env=self.env)

        try:
            snapshots_data = json.loads(result)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Could not parse snapshots JSON: {e}")

        if not isinstance(snapshots_data, list):
            raise RuntimeError("Expected snapshots to be a list")

        snapshots = []
        for snapshot_data in snapshots_data:
            snapshot = ResticSnapshot(
                time=datetime.fromisoformat(
                    snapshot_data["time"].replace("Z", "+00:00")
                ),
                paths=snapshot_data["paths"],
                hostname=snapshot_data["hostname"],
                username=snapshot_data["username"],
                program_version=snapshot_data.get("program_version"),
                id=snapshot_data["id"],
                short_id=snapshot_data["short_id"],
            )
            snapshots.append(snapshot)

        if path_filter is not None:
            filtered_snapshots = []

            resolved_filter = await async_fs.resolve(path_filter)
            for snapshot in snapshots:
                for snapshot_path in snapshot.paths:
                    snapshot_path_resolved = await async_fs.resolve(
                        Path(snapshot_path)
                    )
                    try:
                        resolved_filter.relative_to(snapshot_path_resolved)
                        filtered_snapshots.append(snapshot)
                        break
                    except ValueError:
                        continue

            return filtered_snapshots

        return snapshots

    async def find_snapshots_covering(
        self, paths: List[Path]
    ) -> List[ResticSnapshot]:
        """Snapshots whose recorded paths ancestor-match *every* input path; newest-first."""
        if not paths:
            raise ValueError("At least one path must be provided")
        for path in paths:
            if not path.is_absolute():
                raise ValueError("Paths must be absolute")

        all_snapshots = await self.list_snapshots()

        resolved_paths = [await async_fs.resolve(p) for p in paths]

        # Pre-resolve once so the inner loop stays pure path-math (no syscalls).
        resolved_snapshot_paths: dict[str, list[Path]] = {}
        for snap in all_snapshots:
            resolved_snapshot_paths[snap.id] = [
                await async_fs.resolve(Path(p)) for p in snap.paths
            ]

        def covers(snapshot: ResticSnapshot, target: Path) -> bool:
            for snap_path in resolved_snapshot_paths[snapshot.id]:
                try:
                    target.relative_to(snap_path)
                    return True
                except ValueError:
                    continue
            return False

        matching = [
            s for s in all_snapshots if all(covers(s, p) for p in resolved_paths)
        ]
        matching.sort(key=lambda s: s.time, reverse=True)
        return matching

    @staticmethod
    def compute_restore_destination(target_path: Path, snapshot_path: Path) -> Path:
        """Where a snapshot item lands under ``--target target_path``.

        Restic preserves the absolute path under the target, so with
        ``target_path=Path('/')`` the result equals ``snapshot_path``.
        """
        if not snapshot_path.is_absolute():
            raise ValueError("snapshot_path must be absolute")
        return target_path / snapshot_path.relative_to("/")

    async def restore_preview(
        self,
        snapshot_id: str,
        target_path: Path = Path("/"),
        include_paths: Optional[List[Path]] = None,
    ) -> List[ResticRestorePreviewAction]:
        """Dry-run restore: returns the would-be actions.

        Action ``item`` is the snapshot's original absolute path; use
        ``compute_restore_destination`` to map it to the on-disk location.
        """
        args = [
            "restic",
            "restore",
            snapshot_id,
            "--target",
            str(target_path),
            "--dry-run",
            "-vv",
            "--delete",
            "--json",
        ]

        if include_paths:
            for include_path in include_paths:
                args.extend(["--include", str(include_path)])

        args = self._add_password_args(args)
        result = await exec_command(*args, env=self.env)

        actions = []
        for line in result.strip().split("\n"):
            if not line.strip():
                continue

            try:
                action_data = json.loads(line)
            except json.JSONDecodeError:
                continue

            action = ResticRestorePreviewAction(
                message_type=action_data["message_type"],
                action=action_data.get("action"),
                item=action_data.get("item"),
                size=action_data.get("size"),
            )
            actions.append(action)

        # Drop zero-size "restored" actions (directory entries restic reports but doesn't really restore).
        filtered_actions = []
        for action in actions:
            if action.action in ["updated", "deleted", "restored"]:
                if action.action == "restored" and (
                    action.size is None or action.size == 0
                ):
                    continue
                filtered_actions.append(action)

        return filtered_actions

    async def restore(
        self,
        snapshot_id: str,
        target_path: Path = Path("/"),
        include_paths: Optional[List[Path]] = None,
    ) -> AsyncGenerator[ResticRestoreEvent, None]:
        """Run ``restic restore --json -vv`` and yield ``ResticRestoreEvent`` per NDJSON line.

        ``include_paths`` are absolute snapshot paths (not target-mapped).
        With ``--target /`` restic requires at least one include/exclude
        because ``--delete`` is always passed. ``--delete`` is scoped to
        included roots, leaving siblings under ``target_path`` untouched.

        Raises ``RuntimeError`` (with captured stderr) on non-zero exit.
        """
        args = [
            "restic",
            "restore",
            snapshot_id,
            "--target",
            str(target_path),
            "--delete",
            "--json",
            "-vv",
        ]

        if include_paths:
            for include_path in include_paths:
                args.extend(["--include", str(include_path)])

        args = self._add_password_args(args)

        proc = await asyncio.create_subprocess_exec(
            *args,
            env=self.env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # Drain stderr concurrently to keep the pipe from filling and deadlocking restic.
        stderr_chunks: list[bytes] = []

        async def _drain_stderr() -> None:
            assert proc.stderr is not None
            while True:
                chunk = await proc.stderr.read(4096)
                if not chunk:
                    return
                stderr_chunks.append(chunk)

        drain_task = asyncio.create_task(_drain_stderr())
        try:
            assert proc.stdout is not None
            async for raw in proc.stdout:
                line = raw.decode(errors="replace").strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event = _parse_restore_event(data)
                if event is not None:
                    yield event
            await proc.wait()
            await drain_task
            if proc.returncode != 0:
                stderr = b"".join(stderr_chunks).decode(errors="replace")
                raise RuntimeError(
                    f"restic restore failed (exit {proc.returncode}): {stderr}"
                )
        finally:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
            if not drain_task.done():
                drain_task.cancel()

    async def forget_id(self, snapshot_id: str, prune: bool = True) -> str:
        """Remove the snapshot ``snapshot_id``; prune the repo afterwards by default."""
        args = ["restic", "forget", snapshot_id]

        if prune:
            args.append("--prune")

        args = self._add_password_args(args)
        result = await exec_command(*args, env=self.env)
        return result

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
        """Apply restic ``forget`` retention rules. Raises ``ValueError`` if all are empty."""
        retention_params = [
            keep_last,
            keep_hourly,
            keep_daily,
            keep_weekly,
            keep_monthly,
            keep_yearly,
            keep_tag,
            keep_within,
        ]
        if all(
            param is None
            or (isinstance(param, list) and len(param) == 0)
            or (isinstance(param, str) and param.strip() == "")
            for param in retention_params
        ):
            raise ValueError(
                "At least one retention policy parameter must be specified"
            )

        args = ["restic", "forget", "--group-by", ""]

        if keep_last is not None:
            args.extend(["--keep-last", str(keep_last)])

        if keep_hourly is not None:
            args.extend(["--keep-hourly", str(keep_hourly)])

        if keep_daily is not None:
            args.extend(["--keep-daily", str(keep_daily)])

        if keep_weekly is not None:
            args.extend(["--keep-weekly", str(keep_weekly)])

        if keep_monthly is not None:
            args.extend(["--keep-monthly", str(keep_monthly)])

        if keep_yearly is not None:
            args.extend(["--keep-yearly", str(keep_yearly)])

        if keep_tag is not None and len(keep_tag) > 0:
            for tag in keep_tag:
                args.extend(["--keep-tag", tag])

        if keep_within is not None:
            args.extend(["--keep-within", keep_within])

        if prune:
            args.append("--prune")

        args = self._add_password_args(args)
        result = await exec_command(*args, env=self.env)
        return result

    async def list_locks(self) -> str:
        args = self._add_password_args(["restic", "list", "locks"])
        return await exec_command(*args, env=self.env)

    async def unlock(self) -> str:
        args = self._add_password_args(["restic", "unlock"])
        return await exec_command(*args, env=self.env)


restic_manager = None
if settings.restic:
    restic_manager = ResticManager(
        repository_path=settings.restic.repository_path,
        password=settings.restic.password,
    )
