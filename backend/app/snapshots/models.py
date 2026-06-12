"""Pydantic models and enums shared across the snapshots package."""

from datetime import datetime
from enum import StrEnum
from typing import List, Literal, Optional

from pydantic import BaseModel


class NodeKind(StrEnum):
    """Kind of a node inside a snapshot tree (``restic ls``)."""

    DIR = "dir"
    FILE = "file"


class ResticSnapshot(BaseModel):
    time: datetime
    paths: List[str]
    excludes: List[str] = []
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
    percent_done: Optional[float] = None
    total_files: Optional[int] = None
    files_restored: Optional[int] = None
    files_skipped: Optional[int] = None
    files_deleted: Optional[int] = None
    total_bytes: Optional[int] = None
    bytes_restored: Optional[int] = None
    bytes_skipped: Optional[int] = None
    action: Optional[ResticRestoreAction] = None
    item: Optional[str] = None
    size: Optional[int] = None
