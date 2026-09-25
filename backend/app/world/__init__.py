"""World subsystem: layout discovery, per-server locking, restore orchestration."""

from ..runtime_resources import current_runtime
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
    get_server_operation_lock,
)
from .restore import (
    PreviewEvent,
    RestoreError,
    RestoreEvent,
    SelectionResolutionError,
    ServerNotStoppedError,
    WorldRestoreOrchestrator,
)


def get_world_restore_orchestrator() -> WorldRestoreOrchestrator | None:
    return current_runtime().resource('world_restore_orchestrator')


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
    'get_server_operation_lock',
    'get_world_restore_orchestrator',
    "label_for_dimension_dir",
    "label_for_dimension_path",
    "resolve_dimension_folder",
]
