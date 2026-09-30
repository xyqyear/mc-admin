"""Observe application writes and selected targets without hashing directory trees."""

import hashlib
import json
from pathlib import PurePosixPath

import aiofiles.os as aioos
from sqlalchemy import select

from ..operations.context import current_execution
from ..operations.finalization import finalize
from ..operations.models import OperationJournalEntry
from ..operations.resources import journal_resources
from .restoration_store import SessionFactory
from .scopes import ResolvedScope


async def target_version(resolved: ResolvedScope, sessions: SessionFactory) -> str:
    targets = journal_resources(resolved.servers, resolved.claims)
    own = current_execution()
    latest = ""
    async with sessions() as session:
        records = await session.stream(
            select(
                OperationJournalEntry.operation_id,
                OperationJournalEntry.updated_at,
                OperationJournalEntry.resources_json,
            ).where(OperationJournalEntry.data_changed.is_(True))
        )
        try:
            async for operation_id, updated_at, resources_json in records:
                if own is not None and own.operation_id == operation_id:
                    continue
                for resource in json.loads(resources_json):
                    if resource["kind"] not in {"server", "files", "world", "global"}:
                        continue
                    for target in targets:
                        if (
                            resource["server_id"]
                            and target.server_id
                            and (
                                resource["server_id"] != target.server_id
                                or resource["generation"] != target.generation
                            )
                        ):
                            continue
                        a, b = (
                            PurePosixPath(resource["path"]),
                            PurePosixPath(target.path),
                        )
                        if a.is_relative_to(b) or b.is_relative_to(a):
                            latest = max(
                                latest, f"{updated_at.isoformat()}:{operation_id}"
                            )
        finally:
            await finalize(records.close())
    digest = hashlib.sha256(latest.encode())
    for path in resolved.paths:
        try:
            info = await aioos.stat(path)
            value = (
                str(path),
                info.st_dev,
                info.st_ino,
                info.st_mtime_ns,
                info.st_size,
            )
        except FileNotFoundError:
            value = (str(path), None)
        digest.update(json.dumps(value, separators=(",", ":")).encode())
    return digest.hexdigest()
