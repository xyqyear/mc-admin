"""Restic-backed snapshot subsystem.

``snapshot_service`` is the app-facing singleton (``None`` when restic is
not configured). See ``backend/docs/snapshots.md`` for the architecture.
"""

from ..config import settings
from ..minecraft import docker_mc_manager
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

snapshot_service: SnapshotService | None = None
if settings.restic:
    snapshot_service = SnapshotService(
        ResticClient(
            repository_path=settings.restic.repository_path,
            password=settings.restic.password,
            binary_path=settings.restic_binary_path,
        ),
        docker_mc_manager,
    )

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
    "snapshot_service",
]
