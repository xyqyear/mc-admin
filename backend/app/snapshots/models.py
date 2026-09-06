"""Pydantic models and enums shared across the snapshots package."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class NodeKind(StrEnum):
    """Kind of a node inside a snapshot tree (``restic ls``)."""

    DIR = "dir"
    FILE = "file"


class ResticSnapshot(BaseModel):
    time: datetime
    paths: list[str]
    excludes: list[str] = []
    hostname: str
    username: str
    program_version: str | None = None
    id: str
    short_id: str


class ResticSnapshotSummary(BaseModel):
    backup_start: datetime | None = None
    backup_end: datetime | None = None
    files_new: int | None = None
    files_changed: int | None = None
    files_unmodified: int | None = None
    dirs_new: int | None = None
    dirs_changed: int | None = None
    dirs_unmodified: int | None = None
    data_blobs: int | None = None
    tree_blobs: int | None = None
    data_added: int | None = None
    data_added_packed: int | None = None
    total_files_processed: int | None = None
    total_bytes_processed: int | None = None


class ResticSnapshotWithSummary(ResticSnapshot):
    summary: ResticSnapshotSummary | None = None


ResticRestoreAction = Literal["unchanged", "updated", "restored", "deleted"]


class ResticRestoreEvent(BaseModel):
    """One event from a streaming ``restic restore --json -vv``.

    Kinds: ``status`` (periodic ``percent_done`` ∈ [0, 1]),
    ``file`` (per-file action), ``summary`` (final tallies).

    For ``kind="file"`` the ``item`` is always the absolute on-disk
    destination path — ``ResticClient.restore`` normalizes restic's
    subtree-relative items before yielding.
    """

    kind: Literal["status", "file", "summary"]
    percent_done: float | None = None
    total_files: int | None = None
    files_restored: int | None = None
    files_skipped: int | None = None
    files_deleted: int | None = None
    total_bytes: int | None = None
    bytes_restored: int | None = None
    bytes_skipped: int | None = None
    action: ResticRestoreAction | None = None
    item: str | None = None
    size: int | None = None
