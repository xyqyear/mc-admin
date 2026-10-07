from collections.abc import Sequence
from pathlib import Path

from ..servers.references import resolve_server_ref
from .api_models import SnapshotTargetRules
from .ignores import resolve_server_ignores
from .protection import SnapshotProtection
from .restoration_store import SessionFactory


async def read_target_rules(
    server_id: str,
    *,
    sessions: SessionFactory,
    root: Path,
    ignored_paths: Sequence[str],
) -> SnapshotTargetRules:
    async with sessions() as session:
        reference = await resolve_server_ref(session, server_id, servers_root=root)
    paths = await resolve_server_ignores(reference.data_path, ignored_paths)
    protection = SnapshotProtection.capture(paths)
    return SnapshotTargetRules(
        server_id=reference.server_id,
        server_generation=reference.generation,
        ignored_paths=[path.relative_to(reference.data_path).as_posix() for path in protection.current],
        rules_version=protection.version,
    )
