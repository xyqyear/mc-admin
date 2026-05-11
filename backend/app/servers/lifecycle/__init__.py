"""Server lifecycle module: bundled create/remove orchestrators + sync primitives.

Public API:
- create_server_full, remove_server_full: bundled create/remove operations
- adopt_server_partial, deactivate_server_partial: sync-driven partial operations
- validate_adoption, preview_deactivation: side-effect-free helpers for sync
- Pydantic specs/results: CreateServerSpec, CreateServerResult, RemoveServerResult,
  SyncResult, SyncDryRunEntry, SyncEntryError
"""

from .orchestrators import (
    adopt_server_partial,
    create_server_full,
    deactivate_server_partial,
    remove_server_full,
)
from .primitives import (
    cancel_and_wait_for_tasks,
    cancel_restart_cronjobs_for_server,
    close_open_sessions,
    preview_deactivation,
    validate_adoption,
)
from .types import (
    CreateServerResult,
    CreateServerSpec,
    RemoveServerResult,
    SyncDryRunEntry,
    SyncEntryError,
    SyncResult,
)

__all__ = [
    # Orchestrators
    "create_server_full",
    "remove_server_full",
    "adopt_server_partial",
    "deactivate_server_partial",
    # Primitives
    "cancel_and_wait_for_tasks",
    "cancel_restart_cronjobs_for_server",
    "close_open_sessions",
    "validate_adoption",
    "preview_deactivation",
    # Types
    "CreateServerSpec",
    "CreateServerResult",
    "RemoveServerResult",
    "SyncResult",
    "SyncDryRunEntry",
    "SyncEntryError",
]
