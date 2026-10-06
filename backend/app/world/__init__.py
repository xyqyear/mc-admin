"""World subsystem: layout discovery, per-server locking, restore orchestration."""

from .events import (
    RestoreError,
    SelectionResolutionError,
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
    get_server_operation_lock,
)

__all__ = [
    "DEFAULT_LEVEL_NAME",
    "GLOBAL_LOCK_KEY",
    "DimensionFolderResolution",
    "DimensionInfo",
    "LockHolder",
    "RestoreError",
    "SelectionResolutionError",
    "ServerOperationKind",
    "ServerOperationLock",
    "WorldLayoutDiscoveryError",
    "WorldRoot",
    "WorldRootPath",
    "discover_world_root_paths",
    "discover_world_roots",
    "get_server_operation_lock",
    "resolve_dimension_folder",
]
