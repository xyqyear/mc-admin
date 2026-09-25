"""Restic-backed snapshot subsystem.

``snapshot_service`` is the app-facing singleton (``None`` when restic is
not configured). See ``backend/docs/snapshots.md`` for the architecture.
"""

from ..runtime_resources import current_runtime
from .models import (
    NodeKind,
    ResticRestoreAction,
    ResticRestoreEvent,
    ResticSnapshot,
    ResticSnapshotSummary,
    ResticSnapshotWithSummary,
)
from .planner import TargetIgnoredError
from .restic import ResticClient
from .service import SnapshotService


def get_snapshot_service() -> SnapshotService | None:
    return current_runtime().resource('snapshot_service')

__all__ = [
    "NodeKind",
    "ResticClient",
    "ResticRestoreAction",
    "ResticRestoreEvent",
    "ResticSnapshot",
    "ResticSnapshotSummary",
    "ResticSnapshotWithSummary",
    "SnapshotService",
    "TargetIgnoredError",
    'get_snapshot_service',
]
