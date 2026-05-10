from .crud import (
    create_server_record,
    get_active_server_by_id,
    get_active_servers,
    get_active_servers_map,
    get_server_by_id,
    get_server_db_id,
    mark_server_removed,
)
from .lifecycle import (
    CreateServerResult,
    CreateServerSpec,
    RemoveServerResult,
    SyncDryRunEntry,
    SyncEntryError,
    SyncResult,
    adopt_server_partial,
    cancel_and_wait_for_tasks,
    cancel_restart_cronjobs_for_server,
    close_open_sessions,
    create_server_full,
    deactivate_server_partial,
    preview_deactivation,
    remove_server_full,
    validate_adoption,
)
from .port_utils import (
    check_port_conflicts,
    extract_ports_from_yaml,
    get_server_used_ports,
    get_system_used_ports,
)
from .rebuild import rebuild_server_task

__all__ = [
    # CRUD operations
    "create_server_record",
    "get_active_servers",
    "get_active_servers_map",
    "get_server_by_id",
    "get_server_db_id",
    "mark_server_removed",
    "get_active_server_by_id",
    # Port utilities
    "check_port_conflicts",
    "extract_ports_from_yaml",
    "get_server_used_ports",
    "get_system_used_ports",
    # Rebuild task
    "rebuild_server_task",
    # Lifecycle orchestrators
    "create_server_full",
    "remove_server_full",
    "adopt_server_partial",
    "deactivate_server_partial",
    # Lifecycle primitives
    "cancel_and_wait_for_tasks",
    "cancel_restart_cronjobs_for_server",
    "close_open_sessions",
    "validate_adoption",
    "preview_deactivation",
    # Lifecycle types
    "CreateServerSpec",
    "CreateServerResult",
    "RemoveServerResult",
    "SyncResult",
    "SyncDryRunEntry",
    "SyncEntryError",
]
