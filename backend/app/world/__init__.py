"""World subsystem: layout discovery, per-server locking, restore orchestration."""

from pathlib import Path
from typing import Optional

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


# The singleton is built at FastAPI lifespan startup (after dynamic config has
# been initialized) by ``initialize_world_restore_orchestrator``. Routers
# access it via attribute lookup on this module so they always observe the
# latest binding.
world_restore_orchestrator: Optional[WorldRestoreOrchestrator] = None


def initialize_world_restore_orchestrator() -> Optional[WorldRestoreOrchestrator]:
    """Build the orchestrator singleton from current dependencies.

    Idempotent: returns the existing singleton if already built. Returns
    ``None`` if restic is not configured (no repository).
    """
    global world_restore_orchestrator
    if world_restore_orchestrator is not None:
        return world_restore_orchestrator

    from ..db.database import get_async_session
    from ..dynamic_config import config
    from ..minecraft import docker_mc_manager
    from ..snapshots import restic_manager

    if restic_manager is None:
        return None

    cfg = config.snapshots.world_restore
    world_restore_orchestrator = WorldRestoreOrchestrator(
        restic_manager=restic_manager,
        docker_mc_manager=docker_mc_manager,
        server_operation_lock=server_operation_lock,
        session_factory=get_async_session,
        preview_base_dir=Path(cfg.restore_temp_dir),
        preview_ttl_seconds=cfg.preview_session_ttl_seconds,
        preview_janitor_interval_seconds=cfg.preview_janitor_interval_seconds,
    )
    return world_restore_orchestrator


def reset_world_restore_orchestrator() -> None:
    """Clear the singleton — used by tests to allow reconstruction with fresh config."""
    global world_restore_orchestrator
    world_restore_orchestrator = None


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
    "initialize_world_restore_orchestrator",
    "reset_world_restore_orchestrator",
    "server_operation_lock",
    "world_restore_orchestrator",
]
