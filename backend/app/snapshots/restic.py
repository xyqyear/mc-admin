"""
Restic operations module for snapshot management.

This module provides core restic functionality without knowledge of Minecraft servers.
The actual server path resolution happens in the endpoint functions.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel

from ..config import settings
from ..utils.exec import exec_command


class ResticSnapshot(BaseModel):
    """Pydantic model for restic snapshot data"""

    time: datetime
    paths: List[str]
    hostname: str
    username: str
    program_version: Optional[str] = None
    id: str
    short_id: str


class ResticSnapshotSummary(BaseModel):
    """Pydantic model for snapshot summary data"""

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
    """Extended snapshot model with optional summary"""

    summary: Optional[ResticSnapshotSummary] = None


class ResticRestorePreviewAction(BaseModel):
    """Pydantic model for restore preview action"""

    message_type: str
    action: Optional[str] = None
    item: Optional[str] = None
    size: Optional[int] = None


class ResticManager:
    """Core restic operations manager"""

    def __init__(self, repository_path: str, password: str | None = None):
        """
        Initialize restic manager with repository and optional password

        Args:
            repository_path: Path to restic repository
            password: Repository password (None or empty string for no password)
        """
        self.repository_path = repository_path
        self.password = password
        self.use_password = password is not None and password.strip() != ""

        # Set up environment variables
        self.env = {"RESTIC_REPOSITORY": repository_path}
        if password is not None and self.use_password:
            self.env["RESTIC_PASSWORD"] = password

    def _add_password_args(self, args: list[str]) -> list[str]:
        """Add password-related arguments to restic command"""
        if not self.use_password:
            args.append("--insecure-no-password")
        return args

    async def backup(
        self, path: Path, uid: int | None = None, gid: int | None = None
    ) -> ResticSnapshotWithSummary:
        """
        Create a backup snapshot of the specified path

        Args:
            path: Absolute path to backup
            uid: User ID for command execution
            gid: Group ID for command execution

        Returns:
            Created snapshot information with summary
        """
        if not path.is_absolute():
            raise ValueError("Path must be absolute for restic backup")

        args = self._add_password_args(["restic", "backup", str(path), "--json"])
        result = await exec_command(*args, uid=uid, gid=gid, env=self.env)

        # Parse the backup result to get summary and snapshot_id
        lines = result.strip().split("\n")
        summary_data = None
        snapshot_id = None

        # Look for the summary line which contains backup stats and snapshot_id
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

        # Now get the full snapshot information using the snapshot_id
        args = self._add_password_args(["restic", "snapshots", snapshot_id, "--json"])
        snapshots_result = await exec_command(*args, uid=uid, gid=gid, env=self.env)

        try:
            snapshots_list = json.loads(snapshots_result)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Could not parse snapshot info JSON: {e}")

        if not snapshots_list or not isinstance(snapshots_list, list):
            raise RuntimeError("Expected snapshots list from restic")

        snapshot_info = snapshots_list[0]  # Should have exactly one snapshot

        # Create summary object from backup summary data
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

        # Convert to our model using snapshot info + summary
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
        self,
        path_filter: Optional[Path] = None,
        uid: int | None = None,
        gid: int | None = None,
    ) -> List[ResticSnapshot]:
        """
        List all snapshots, optionally filtered by path

        Args:
            path_filter: Optional path to filter snapshots by
            uid: User ID for command execution
            gid: Group ID for command execution

        Returns:
            List of snapshots
        """
        args = self._add_password_args(["restic", "snapshots", "--json"])
        result = await exec_command(*args, uid=uid, gid=gid, env=self.env)

        try:
            snapshots_data = json.loads(result)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Could not parse snapshots JSON: {e}")

        if not isinstance(snapshots_data, list):
            raise RuntimeError("Expected snapshots to be a list")

        # Convert to our models
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

        # Filter snapshots if path_filter is provided
        if path_filter is not None:
            filtered_snapshots = []

            for snapshot in snapshots:
                # Check if any of the snapshot paths is a parent or equal to filter_path
                for snapshot_path in snapshot.paths:
                    snapshot_path_obj = Path(snapshot_path)
                    try:
                        # Check if filter_path is equal to or child of snapshot_path
                        path_filter.resolve().relative_to(snapshot_path_obj.resolve())
                        filtered_snapshots.append(snapshot)
                        break
                    except ValueError:
                        # filter_path is not relative to snapshot_path, continue
                        continue

            return filtered_snapshots

        return snapshots

    async def restore_preview(
        self,
        snapshot_id: str,
        target_path: Path,
        include_path: Optional[Path] = None,
        uid: int | None = None,
        gid: int | None = None,
    ) -> List[ResticRestorePreviewAction]:
        """
        Preview restore operation (dry run)

        Args:
            snapshot_id: Snapshot ID to restore
            target_path: Target path for restore (usually "/" for in-place restore)
            include_path: Optional path to include (filter what gets restored)
            uid: User ID for command execution
            gid: Group ID for command execution

        Returns:
            List of restore actions that would be performed
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

        if include_path:
            args.extend(["--include", str(include_path)])

        args = self._add_password_args(args)
        result = await exec_command(*args, uid=uid, gid=gid, env=self.env)

        actions = []
        for line in result.strip().split("\n"):
            if not line.strip():
                continue

            try:
                action_data = json.loads(line)
            except json.JSONDecodeError:
                # Skip lines that aren't valid JSON
                continue

            action = ResticRestorePreviewAction(
                message_type=action_data["message_type"],
                action=action_data.get("action"),
                item=action_data.get("item"),
                size=action_data.get("size"),
            )
            actions.append(action)

        # Filter actions: include updated, deleted, and restored operations
        # Only exclude restored operations with zero size
        filtered_actions = []
        for action in actions:
            if action.action in ["updated", "deleted", "restored"]:
                # Exclude restored operations with zero or None size
                if action.action == "restored" and (
                    action.size is None or action.size == 0
                ):
                    continue
                filtered_actions.append(action)

        return filtered_actions

    async def restore(
        self,
        snapshot_id: str,
        target_path: Path,
        include_path: Optional[Path] = None,
        uid: int | None = None,
        gid: int | None = None,
    ) -> None:
        """
        Restore snapshot

        Args:
            snapshot_id: Snapshot ID to restore
            target_path: Target path for restore (usually "/" for in-place restore)
            include_path: Optional path to include (filter what gets restored)
            uid: User ID for command execution
            gid: Group ID for command execution
        """
        args = [
            "restic",
            "restore",
            snapshot_id,
            "--target",
            str(target_path),
            "--delete",
        ]

        if include_path:
            args.extend(["--include", str(include_path)])

        args = self._add_password_args(args)
        await exec_command(*args, uid=uid, gid=gid, env=self.env)

    async def forget_id(
        self,
        snapshot_id: str,
        prune: bool = True,
        uid: int | None = None,
        gid: int | None = None,
    ) -> str:
        """
        Remove a specific snapshot by ID

        Args:
            snapshot_id: Snapshot ID to remove
            prune: Whether to run prune after forget (default: True)
            uid: User ID for command execution
            gid: Group ID for command execution

        Returns:
            Command output
        """
        args = ["restic", "forget", snapshot_id]

        # Add prune option if enabled
        if prune:
            args.append("--prune")

        args = self._add_password_args(args)
        result = await exec_command(*args, uid=uid, gid=gid, env=self.env)
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
        uid: int | None = None,
        gid: int | None = None,
    ) -> str:
        """
        Remove snapshots according to retention policy

        Args:
            keep_last: Keep the n last (most recent) snapshots
            keep_hourly: For the last n hours which have one or more snapshots, keep only the most recent one for each hour
            keep_daily: For the last n days which have one or more snapshots, keep only the most recent one for each day
            keep_weekly: For the last n weeks which have one or more snapshots, keep only the most recent one for each week
            keep_monthly: For the last n months which have one or more snapshots, keep only the most recent one for each month
            keep_yearly: For the last n years which have one or more snapshots, keep only the most recent one for each year
            keep_tag: Keep all snapshots which have all tags specified (can be specified multiple times)
            keep_within: Keep all snapshots having a timestamp within the specified duration of the latest snapshot
            prune: Whether to run prune after forget (default: True)
            uid: User ID for command execution
            gid: Group ID for command execution

        Returns:
            Command output

        Raises:
            ValueError: If no retention policy is specified
        """
        # Check that at least one retention policy is specified
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

        args = ["restic", "forget", "--group-by", "''"]

        # Add retention policy arguments
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

        # Add prune option if enabled
        if prune:
            args.append("--prune")

        args = self._add_password_args(args)
        result = await exec_command(*args, uid=uid, gid=gid, env=self.env)
        return result


# Singleton instance - only create if restic settings are available
restic_manager = None
if settings.restic:
    restic_manager = ResticManager(
        repository_path=settings.restic.repository_path,
        password=settings.restic.password,
    )
