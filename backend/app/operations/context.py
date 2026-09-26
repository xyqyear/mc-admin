"""Execution ownership inherited by an operation's adapter calls."""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

from anyio.lowlevel import checkpoint_if_cancelled

from .finalization import finalize
from .journal_types import OperationState, RecoveryReference

if TYPE_CHECKING:
    from ..servers.references import ServerRef
    from .journal import OperationJournal


@dataclass
class OperationExecution:
    journal: "OperationJournal"
    operation_id: str
    servers: tuple["ServerRef", ...] = ()
    outcome: OperationState | None = None
    cache_degraded: bool = False
    settled: bool = False
    failure_code: str | None = None


_execution: ContextVar[OperationExecution | None] = ContextVar("mc_admin_operation", default=None)


def current_execution() -> OperationExecution | None:
    return _execution.get()


@contextmanager
def bind_execution(execution: OperationExecution | None) -> Iterator[None]:
    token = _execution.set(execution)
    try:
        yield
    finally:
        _execution.reset(token)


async def revalidate_targets() -> None:
    execution = current_execution()
    if execution is None:
        return
    from ..db.database import get_async_session
    from ..servers.references import revalidate_server_ref

    await checkpoint_if_cancelled()

    async def read_targets() -> None:
        async with get_async_session() as db:
            for server in execution.servers:
                await revalidate_server_ref(db, server)

    # Finish cursor consumption and session closure before cancellation can trigger journal writes.
    try:
        await finalize(read_targets())
    except Exception as error:
        try:
            await checkpoint_if_cancelled()
        except asyncio.CancelledError as cancelled:
            raise cancelled from error
        raise
    await checkpoint_if_cancelled()


async def record_phase(phase: str, *, changed: bool = False) -> None:
    execution = current_execution()
    if execution is not None:
        await execution.journal.phase(execution.operation_id, phase, changed=changed)


async def retain_recovery_reference(kind: str, value: str) -> None:
    execution = current_execution()
    if execution is not None:
        await execution.journal.phase(
            execution.operation_id, "recovery_available",
            recovery_refs=(RecoveryReference(kind, value),),
        )


async def mark_cache_degraded(server_id: str) -> None:
    from ..runtime_resources import current_runtime
    from .journal_types import ResourceReference

    execution = current_execution()
    if execution is None:
        return
    await execution.journal.mark_cache_degraded(execution.operation_id)
    execution.cache_degraded = True
    recovery = current_runtime().resources.get("operation_recovery")
    if recovery is not None:
        for server in execution.servers:
            if server.server_id == server_id:
                recovery.degraded_resources.add(ResourceReference("cache", server_id, server.generation))
