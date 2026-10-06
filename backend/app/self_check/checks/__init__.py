"""Built-in self-check catalog grouped by operational category."""

from ..constants import CHECK_IDS
from . import backup, dependency, dns, files, locks, log_monitor, server, storage
from .base import (
    CheckDefinition,
    SelfCheckContext,
    finding,
    skipped,
    success,
    usage_percent,
)
from .files import PermissionScanResult
from .server import BackupJarMatch


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
    "CHECK_DEFINITIONS",
    "BackupJarMatch",
    "CheckDefinition",
    "PermissionScanResult",
    "SelfCheckContext",
    "finding",
    "skipped",
    "success",
    "usage_percent",
]
