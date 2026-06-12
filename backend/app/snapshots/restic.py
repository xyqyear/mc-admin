"""ResticClient: a stateless async wrapper around the restic CLI.

Every method maps to one restic invocation; business logic (ignore paths,
restore planning, path coverage) lives in the rest of the package.

Restore is always subtree-addressed (``<snapshot>:<source_dir>``) so that
``--exclude`` can protect on-disk paths from ``--delete`` — restic forbids
combining ``--include`` with ``--exclude``, and patterns match relative to
the subtree root, never against original absolute paths.
"""

import asyncio
import json
from collections.abc import AsyncGenerator, Sequence
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ..config import settings
from ..utils.exec import exec_command
from .models import (
    NodeKind,
    ResticRestoreEvent,
    ResticSnapshot,
    ResticSnapshotSummary,
    ResticSnapshotWithSummary,
)


def _snapshot_from_json(data: dict) -> ResticSnapshot:
    return ResticSnapshot(
        time=datetime.fromisoformat(data["time"].replace("Z", "+00:00")),
        paths=data["paths"],
        excludes=data.get("excludes") or [],
        hostname=data["hostname"],
        username=data["username"],
        program_version=data.get("program_version"),
        id=data["id"],
        short_id=data["short_id"],
    )


def _parse_restore_event(
    data: dict, target_dir: Path
) -> Optional[ResticRestoreEvent]:
    """Convert one decoded JSON line into a normalized ``ResticRestoreEvent``.

    Restic reports restored/updated/unchanged items relative to the restore
    subtree but deleted items as absolute on-disk paths; both are normalized
    to absolute on-disk paths here.
    """
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
        item = data.get("item")
        if item is not None and action != "deleted":
            item = str(target_dir / item.lstrip("/"))
        return ResticRestoreEvent(
            kind="file",
            action=action,
            item=item,
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


class ResticClient:
    def __init__(
        self,
        repository_path: str,
        password: str | None = None,
        binary_path: str | Path | None = None,
    ):
        """``password=None`` or empty string means the repository is unprotected."""
        self.repository_path = repository_path
        self.binary_path = Path(binary_path or settings.restic_binary_path)
        password_value = (
            password if password is not None and password.strip() != "" else None
        )
        self.use_password = password_value is not None

        self.env = {"RESTIC_REPOSITORY": repository_path}
        if password_value is not None:
            self.env["RESTIC_PASSWORD"] = password_value

    def _build_args(self, *args: str) -> list[str]:
        full = [str(self.binary_path), *args]
        if not self.use_password:
            full.append("--insecure-no-password")
        return full

    async def _run(self, *args: str) -> str:
        full = self._build_args(*args)
        return await exec_command(*full, env=self.env)

    async def backup(
        self, paths: Sequence[Path], excludes: Sequence[str] = ()
    ) -> ResticSnapshotWithSummary:
        """Capture the given absolute paths into one snapshot.

        ``excludes`` are absolute path patterns; restic records them in the
        snapshot metadata, which restore later unions with current config.
        """
        if not paths:
            raise ValueError("At least one path must be provided for restic backup")
        for path in paths:
            if not path.is_absolute():
                raise ValueError("Path must be absolute for restic backup")

        args = ["backup", *(str(p) for p in paths)]
        for pattern in excludes:
            args.extend(["--exclude", pattern])
        args.append("--json")
        result = await self._run(*args)

        summary_data = None
        snapshot_id = None
        for line in reversed(result.strip().split("\n")):
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

        snapshot = await self.get_snapshot(snapshot_id)

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
            **snapshot.model_dump(),
            summary=summary,
        )

    async def get_snapshot(self, snapshot_id: str) -> ResticSnapshot:
        result = await self._run("snapshots", snapshot_id, "--json")
        try:
            snapshots = json.loads(result)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Could not parse snapshot info JSON: {e}")
        if not isinstance(snapshots, list) or not snapshots:
            raise RuntimeError(f"Snapshot not found: {snapshot_id}")
        return _snapshot_from_json(snapshots[0])

    async def list_snapshots(self) -> List[ResticSnapshot]:
        result = await self._run("snapshots", "--json")
        try:
            snapshots_data = json.loads(result)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Could not parse snapshots JSON: {e}")
        if not isinstance(snapshots_data, list):
            raise RuntimeError("Expected snapshots to be a list")
        return [_snapshot_from_json(d) for d in snapshots_data]

    async def ls(self, snapshot_id: str, path: Path) -> dict[Path, NodeKind]:
        """One-level listing of ``path`` inside the snapshot.

        Maps absolute snapshot paths (the node itself plus direct children)
        to node kinds; non-directory nodes all map to ``FILE``. An empty dict
        means the path is not present in the snapshot.
        """
        if not path.is_absolute():
            raise ValueError("ls path must be absolute")
        result = await self._run("ls", snapshot_id, str(path), "--json")

        nodes: dict[Path, NodeKind] = {}
        for line in result.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if data.get("struct_type") != "node" and data.get("message_type") != "node":
                continue
            node_path = data.get("path")
            node_type = data.get("type")
            if not node_path or not node_type:
                continue
            kind = NodeKind.DIR if node_type == "dir" else NodeKind.FILE
            nodes[Path(node_path)] = kind
        return nodes

    async def restore(
        self,
        snapshot_id: str,
        *,
        source_dir: Path,
        target_dir: Path,
        excludes: Sequence[str] = (),
        includes: Sequence[str] = (),
        delete: bool = False,
        dry_run: bool = False,
    ) -> AsyncGenerator[ResticRestoreEvent, None]:
        """Stream ``restic restore <snapshot>:<source_dir> --target <target_dir>``.

        ``excludes`` / ``includes`` are subtree-relative patterns (leading
        ``/`` anchors at ``source_dir``); restic forbids passing both.
        ``delete`` removes on-disk files under ``target_dir`` that the
        snapshot lacks — scoped to includes when includes are given, and
        never touching excluded paths.

        Raises ``RuntimeError`` (with captured stderr) on non-zero exit.
        """
        if excludes and includes:
            raise ValueError("restic forbids combining --include with --exclude")
        if not source_dir.is_absolute() or not target_dir.is_absolute():
            raise ValueError("source_dir and target_dir must be absolute")

        args = [
            "restore",
            f"{snapshot_id}:{source_dir}",
            "--target",
            str(target_dir),
            "--json",
            "-vv",
        ]
        if delete:
            args.append("--delete")
        if dry_run:
            args.append("--dry-run")
        for pattern in excludes:
            args.extend(["--exclude", pattern])
        for pattern in includes:
            args.extend(["--include", pattern])
        full_args = self._build_args(*args)

        proc = await asyncio.create_subprocess_exec(
            *full_args,
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
                event = _parse_restore_event(data, target_dir)
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
        args = ["forget", snapshot_id]
        if prune:
            args.append("--prune")
        return await self._run(*args)

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

        args = ["forget", "--group-by", ""]
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
        if keep_tag:
            for tag in keep_tag:
                args.extend(["--keep-tag", tag])
        if keep_within is not None:
            args.extend(["--keep-within", keep_within])
        if prune:
            args.append("--prune")
        return await self._run(*args)

    async def list_locks(self) -> str:
        return await self._run("list", "locks")

    async def unlock(self) -> str:
        return await self._run("unlock")
