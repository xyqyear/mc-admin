"""Built-in self-check catalog grouped by operational category."""

from ..constants import CHECK_IDS
from . import backup, dependency, dns, files, locks, log_monitor, server, storage
from .base import (
    CheckDefinition,
    SelfCheckContext,
    _finding,
    _skipped,
    _success,
    _usage_percent,
    finding,
    skipped,
    success,
    usage_percent,
)
from .files import PermissionScanResult, _scan_permission_owner_with_fd
from .server import BackupJarMatch, _find_backup_jars_sync


def _merge_definitions() -> dict[str, CheckDefinition]:
    definitions: dict[str, CheckDefinition] = {}
    for module in (
        backup,
        storage,
        locks,
        dns,
        dependency,
        log_monitor,
        server,
        files,
    ):
        definitions.update(module.DEFINITIONS)

    missing = [check_id for check_id in CHECK_IDS if check_id not in definitions]
    extra = sorted(set(definitions) - set(CHECK_IDS))
    if missing or extra:
        raise RuntimeError(
            f"self-check catalog mismatch: missing={missing}, extra={extra}"
        )

    return {
        check_id: definitions[check_id]
        for check_id in CHECK_IDS
    }


CHECK_DEFINITIONS = _merge_definitions()


__all__ = [
    "BackupJarMatch",
    "CHECK_DEFINITIONS",
    "CheckDefinition",
    "PermissionScanResult",
    "SelfCheckContext",
    "_find_backup_jars_sync",
    "_finding",
    "_scan_permission_owner_with_fd",
    "_skipped",
    "_success",
    "_usage_percent",
    "finding",
    "skipped",
    "success",
    "usage_percent",
]
