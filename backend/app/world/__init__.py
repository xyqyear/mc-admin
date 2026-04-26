"""World subsystem: layout discovery, per-server locking, restore orchestration."""

from .layout import (
    DEFAULT_LEVEL_NAME,
    DimensionInfo,
    WorldRoot,
    discover_world_roots,
)
from .locks import (
    GLOBAL_LOCK_KEY,
    LockHolder,
    ServerOperationKind,
    ServerOperationLock,
    server_operation_lock,
)
from .restore import (
    PreviewEvent,
    RestoreError,
    RestoreEvent,
    SelectionResolutionError,
    ServerNotStoppedError,
    WorldRestoreOrchestrator,
)


def _build_orchestrator() -> "WorldRestoreOrchestrator | None":
    from ..db.database import get_async_session
    from ..minecraft import docker_mc_manager
    from ..snapshots import restic_manager

    if restic_manager is None:
        return None
    return WorldRestoreOrchestrator(
        restic_manager=restic_manager,
        docker_mc_manager=docker_mc_manager,
        server_operation_lock=server_operation_lock,
        session_factory=get_async_session,
    )


world_restore_orchestrator = _build_orchestrator()


__all__ = [
    "DEFAULT_LEVEL_NAME",
    "DimensionInfo",
    "GLOBAL_LOCK_KEY",
    "LockHolder",
    "PreviewEvent",
    "RestoreError",
    "RestoreEvent",
    "SelectionResolutionError",
    "ServerNotStoppedError",
    "ServerOperationKind",
    "ServerOperationLock",
    "WorldRestoreOrchestrator",
    "WorldRoot",
    "discover_world_roots",
    "server_operation_lock",
    "world_restore_orchestrator",
]
