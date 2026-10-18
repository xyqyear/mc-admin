import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.operations.journal import JournalCapacityError
from app.operations.journal_types import (
    JournalLimits,
    OperationSpec,
    OperationState,
    RecoveryReference,
    ResourceReference,
)
from app.operations.models import OperationJournalEntry


def restoration(identity: str) -> OperationSpec:
    return OperationSpec("snapshot_restore", (ResourceReference("files", "survival", 1),), operation_id=identity)


HISTORY = (
    RecoveryReference("source_snapshot", "source"),
    RecoveryReference("restoration", "history"),
    RecoveryReference("safety_snapshot", "safety"),
)


async def test_successful_restoration_history_does_not_exhaust_admission(journal):
    journal.limits = JournalLimits(max_records=2)
    for index in range(5):
        identity = str(index)
        await journal.accept(restoration(identity))
        await journal.phase(identity, "safety_saved", recovery_refs=HISTORY)
        record = await journal.finish(identity, OperationState.SUCCEEDED, writers_stopped=True)
        assert record.recovery_refs == tuple(RecoveryReference(value.kind, value.value, resolved=True) for value in HISTORY)
    await journal.accept(OperationSpec("dns_update", (ResourceReference("global"),), operation_id="unrelated"))
    assert len(await journal.list()) == 2


async def test_pruning_reconciles_safe_successful_legacy_history_without_touching_staging(journal):
    old = datetime(2026, 1, 1, tzinfo=UTC)
    journal.clock = lambda: old
    for identity in ("legacy", "staging"):
        await journal.accept(restoration(identity))
        await journal.finish(identity, OperationState.SUCCEEDED, writers_stopped=True, recovery_refs=HISTORY)
    stage = RecoveryReference("archive_stage", "retained-stage")
    async with journal.session_factory() as session, session.begin():
        for identity, references in (("legacy", HISTORY), ("staging", (*HISTORY, stage))):
            await session.execute(update(OperationJournalEntry).where(OperationJournalEntry.operation_id == identity).values(
                has_recovery_refs=True,
                recovery_refs_json=json.dumps([{"kind": value.kind, "value": value.value, "resolved": False} for value in references]),
            ))
    journal.clock = lambda: old + timedelta(days=365)
    assert await journal.prune() == 1
    assert await journal.get("legacy") is None
    retained = await journal.get("staging")
    assert retained is not None
    assert retained.recovery_refs[-1] == stage
    assert all(reference.resolved for reference in retained.recovery_refs[:-1])
    assert [record.operation_id for record in await journal.unsettled()] == ["staging"]


@pytest.mark.parametrize("state,stopped,degraded,blocked", [
    (OperationState.FAILED, True, False, None),
    (OperationState.CANCELLED, True, False, None),
    (OperationState.INTERRUPTED, False, False, None),
    (OperationState.SUCCEEDED, True, True, None),
    (OperationState.SUCCEEDED, True, False, "manual_verification"),
])
async def test_unresolved_restoration_recovery_stays_protected(journal, state, stopped, degraded, blocked):
    journal.limits = JournalLimits(max_records=1)
    await journal.accept(restoration("protected"))
    record = await journal.finish("protected", state, writers_stopped=stopped, cache_degraded=degraded,
                                  blocked_reason=blocked, recovery_refs=HISTORY)
    assert record.recovery_refs == HISTORY
    journal.clock = lambda: datetime.now(UTC) + timedelta(days=365)
    assert await journal.prune() == 0
    with pytest.raises(JournalCapacityError):
        await journal.accept(restoration("new"))
    assert (await journal.get("protected")).recovery_refs == HISTORY
