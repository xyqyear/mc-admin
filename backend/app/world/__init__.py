"""World subsystem: layout discovery, per-server locking, restore orchestration."""

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
world_restore_orchestrator: WorldRestoreOrchestrator | None = None


def initialize_world_restore_orchestrator() -> WorldRestoreOrchestrator | None:
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
    "GLOBAL_LOCK_KEY",
    "DimensionFolderResolution",
    "DimensionInfo",
    "LockHolder",
    "PreviewEvent",
    "RestoreError",
    "RestoreEvent",
    "SelectionResolutionError",
    "ServerNotStoppedError",
    "ServerOperationKind",
    "ServerOperationLock",
    "WorldLayoutDiscoveryError",
    "WorldRestoreOrchestrator",
    "WorldRoot",
    "WorldRootPath",
    "dimension_path_for_dir",
    "discover_world_root_paths",
    "discover_world_roots",
    "initialize_world_restore_orchestrator",
    "label_for_dimension_dir",
    "label_for_dimension_path",
    "reset_world_restore_orchestrator",
    "resolve_dimension_folder",
    "server_operation_lock",
    "world_restore_orchestrator",
]
