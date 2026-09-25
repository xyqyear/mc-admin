"""Retain daemon mutation ownership until the caller can release its lease."""

import asyncio
from collections.abc import Awaitable, Callable

from .context import current_execution, record_phase
from .execution import settle_execution
from .finalization import finalize
from .journal_types import OperationState


async def run_daemon_mutation(
    command: Callable[[], Awaitable[None]], *, phase: str, completed_phase: str,
    running_intent: bool,
    settle_on_failure: bool = True,
) -> None:
    execution = current_execution()
    if execution is not None:
        await execution.journal.capture_running_intent(execution.operation_id, running_intent)
    await record_phase(phase, changed=True)
    dispatched = False
    try:
        if execution is not None:
            await execution.journal.set_ownership_known(execution.operation_id, False)
        dispatched = True
        await command()
        if execution is not None:
            await execution.journal.set_ownership_known(execution.operation_id, True)
        await record_phase(completed_phase, changed=True)
    except BaseException as failure:
        cancelled = isinstance(failure, (asyncio.CancelledError, GeneratorExit))
        if execution is not None:
            async def settle_failure() -> None:
                if not dispatched:
                    await execution.journal.set_ownership_known(execution.operation_id, True)
                if not settle_on_failure:
                    return
                record = await execution.journal.get(execution.operation_id)
                state = OperationState.FAILED
                if cancelled:
                    state = OperationState.INTERRUPTED if record is not None and record.origin == "request" else OperationState.CANCELLED
                await settle_execution(execution, state)

            try:
                await finalize(settle_failure())
            except BaseException as settlement_failure:
                raise failure from settlement_failure
        raise
