"""World subsystem: layout discovery, per-server locking, restore orchestration."""

from typing import Optional

from .dimension_labels import (
    DIMENSION_LABELS,
    END_LABEL,
    NETHER_LABEL,
    OVERWORLD_LABEL,
    dimension_path_for_dir,
    label_for_dimension_dir,
    label_for_dimension_path,
)
from .layout import (
    DEFAULT_LEVEL_NAME,
    DimensionInfo,
    WorldLayoutDiscoveryError,
    WorldRoot,
    discover_world_roots,
)
from .layout_cache import (
    clear_world_layout_cache,
    get_cached_world_roots,
    invalidate_world_layout,
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
    from ..snapshots import restic_manager

    if restic_manager is None:
        return None

    world_restore_orchestrator = WorldRestoreOrchestrator(
        restic_manager=restic_manager,
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
    "DIMENSION_LABELS",
    "DimensionInfo",
    "END_LABEL",
    "GLOBAL_LOCK_KEY",
    "LockHolder",
    "NETHER_LABEL",
    "OVERWORLD_LABEL",
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
    "clear_world_layout_cache",
    "discover_world_roots",
    "dimension_path_for_dir",
    "get_cached_world_roots",
    "initialize_world_restore_orchestrator",
    "invalidate_world_layout",
    "label_for_dimension_dir",
    "label_for_dimension_path",
    "reset_world_restore_orchestrator",
    "server_operation_lock",
    "world_restore_orchestrator",
]
