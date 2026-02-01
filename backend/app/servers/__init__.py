"""Server database operations and utilities for MC Admin.

Provides CRUD operations for server records, port conflict checking, and rebuild tasks.
"""

from .crud import (
    create_server_record,
    get_active_server_by_id,
    get_active_servers,
    get_active_servers_map,
    get_server_by_id,
    get_server_db_id,
    mark_server_removed,
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
]
