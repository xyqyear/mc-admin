"""World subsystem: layout discovery, per-server locking, restore orchestration."""

from typing import Optional

from .dimension_labels import (
    dimension_path_for_dir,
    label_for_dimension_dir,
    label_for_dimension_path,
)
from .layout import (
    DEFAULT_LEVEL_NAME,
    DimensionFolderResolution,
    DimensionInfo,
    WorldLayoutDiscoveryError,
    WorldRoot,
    WorldRootPath,
    discover_world_root_paths,
    discover_world_roots,
    resolve_dimension_folder,
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


# Built at lifespan startup; routers do attribute lookup so they observe the latest binding.
world_restore_orchestrator: Optional[WorldRestoreOrchestrator] = None


def initialize_world_restore_orchestrator() -> Optional[WorldRestoreOrchestrator]:
    """Build the orchestrator singleton; ``None`` if restic isn't configured. Idempotent."""
    global world_restore_orchestrator
    if world_restore_orchestrator is not None:
        return world_restore_orchestrator

    from ..db.database import get_async_session
    from ..minecraft import docker_mc_manager
    from ..snapshots import snapshot_service

    if snapshot_service is None:
        return None

    world_restore_orchestrator = WorldRestoreOrchestrator(
        snapshot_service=snapshot_service,
        docker_mc_manager=docker_mc_manager,
        server_operation_lock=server_operation_lock,
        session_factory=get_async_session,
    )
    return world_restore_orchestrator


def reset_world_restore_orchestrator() -> None:
    """Clear the singleton — used by tests to allow reconstruction with fresh config."""
    global world_restore_orchestrator
    world_restore_orchestrator = None


__all__ = [
    "DEFAULT_LEVEL_NAME",
    "DimensionFolderResolution",
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
    "WorldLayoutDiscoveryError",
    "WorldRoot",
    "WorldRootPath",
    "discover_world_root_paths",
    "discover_world_roots",
    "dimension_path_for_dir",
    "initialize_world_restore_orchestrator",
    "label_for_dimension_dir",
    "label_for_dimension_path",
    "resolve_dimension_folder",
    "reset_world_restore_orchestrator",
    "server_operation_lock",
    "world_restore_orchestrator",
]
