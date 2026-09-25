import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.operations.journal import (
    InvalidOperationTransition,
    JournalCapacityError,
    OperationJournal,
)
from app.operations.journal_types import (
    JournalLimits,
    OperationSpec,
    OperationState,
    ProcessIdentity,
    RecoveryReference,
    ResourceReference,
)
from app.operations.models import OperationJournalEntry

RESOURCE = ResourceReference("world", "survival", 12, "world")


def spec(identity: str, **values) -> OperationSpec:
    return OperationSpec("world_restore", (RESOURCE,), operation_id=identity, **values)


async def test_durable_phase_actor_generation_and_recovery_survive_new_store(journal):
    await journal.accept(spec("restore", actor_id=41, origin="request", legacy_id="restoration-42"))
    await journal.start("restore")
    await journal.capture_running_intent("restore", True)
    await journal.phase("restore", "data_changed", changed=True, recovery_refs=[RecoveryReference("snapshot", "a" * 64)])
    await journal.finish("restore", OperationState.INTERRUPTED, writers_stopped=True, failure_code="stream_closed")
    reopened = OperationJournal(journal.session_factory)
    record = await reopened.get("restore")
    assert record is not None
    assert (record.actor_id, record.resources, record.legacy_id) == (41, (RESOURCE,), "restoration-42")
    assert record.state == OperationState.INTERRUPTED
    assert record.phase == "data_changed"
    assert record.data_changed and record.writers_stopped
    assert record.running_intent is True
    assert record.recovery_refs == (RecoveryReference("snapshot", "a" * 64),)
    assert record.ended_at is not None
    with pytest.raises(InvalidOperationTransition):
        await journal.capture_running_intent("restore", False)


async def test_cancellation_cannot_finish_before_owned_process_cleanup(journal):
    await journal.accept(spec("cancel"))
    await journal.start("cancel")
    identity = ProcessIdentity(123, 123, 456, "synthetic-boot", 12, 34)
    await journal.register_process("cancel", identity)
    await journal.phase("cancel", "stopping_process", state=OperationState.CANCELLING)
    with pytest.raises(InvalidOperationTransition):
        await journal.finish("cancel", OperationState.CANCELLED, writers_stopped=True)
    with pytest.raises(InvalidOperationTransition):
        await journal.finish("cancel", OperationState.CANCELLED, writers_stopped=False)
    assert not await journal.process_stopped("cancel", 123, 999)
    assert await journal.process_stopped("cancel", 123, 456)
    finished = await journal.finish("cancel", OperationState.CANCELLED, writers_stopped=True)
    assert finished.processes == ()
    assert finished.state == OperationState.CANCELLED


async def test_unknown_daemon_ownership_cannot_claim_terminal_success(journal):
    await journal.accept(spec("daemon"))
    await journal.start("daemon")
    await journal.set_ownership_known("daemon", False)
    with pytest.raises(InvalidOperationTransition):
        await journal.finish("daemon", OperationState.SUCCEEDED, writers_stopped=True)
    record = await journal.finish("daemon", OperationState.INTERRUPTED, writers_stopped=False)
    assert record.blocked_reason == "writers_unconfirmed"
    assert not record.ownership_known
    with pytest.raises(InvalidOperationTransition):
        await journal.set_ownership_known("daemon", True)


async def test_uncertainty_never_keeps_a_queued_stopped_assertion(journal):
    await journal.accept(spec("uncertain"))
    await journal.set_ownership_known("uncertain", False)
    record = await journal.get("uncertain")
    assert record is not None
    assert not record.ownership_known and not record.writers_stopped


async def test_terminal_outcome_is_immutable_under_concurrent_completion(journal):
    await journal.accept(spec("terminal"))
    await journal.start("terminal")
    results = await asyncio.gather(
        journal.finish("terminal", OperationState.SUCCEEDED, writers_stopped=True),
        journal.finish("terminal", OperationState.FAILED, writers_stopped=True),
        return_exceptions=True,
    )
    assert sum(isinstance(result, InvalidOperationTransition) for result in results) == 1
    with pytest.raises(InvalidOperationTransition):
        await journal.phase("terminal", "late_progress")


async def test_capacity_evicts_only_unprotected_terminal_history(journal):
    journal.limits = JournalLimits(max_records=4)
    await journal.accept(spec("active"))
    await journal.accept(spec("blocked"))
    await journal.start("blocked")
    await journal.finish("blocked", OperationState.INTERRUPTED, writers_stopped=False)
    await journal.accept(spec("retained-reference"))
    await journal.finish("retained-reference", OperationState.FAILED, writers_stopped=True,
                         recovery_refs=[RecoveryReference("snapshot", "b" * 64)])
    await journal.accept(spec("evictable"))
    await journal.finish("evictable", OperationState.SUCCEEDED, writers_stopped=True)
    await journal.accept(spec("replacement"))
    assert await journal.get("evictable") is None
    assert {record.operation_id for record in await journal.list()} == {
        "active", "blocked", "retained-reference", "replacement",
    }
    with pytest.raises(JournalCapacityError):
        await journal.accept(spec("overflow"))
    assert len(await journal.list()) == 4


async def test_cross_store_capacity_admission_is_atomic(journal):
    first = OperationJournal(journal.session_factory, limits=JournalLimits(max_records=1))
    second = OperationJournal(journal.session_factory, limits=JournalLimits(max_records=1))
    results = await asyncio.gather(first.accept(spec("one")), second.accept(spec("two")), return_exceptions=True)
    assert sum(isinstance(result, JournalCapacityError) for result in results) == 1
    assert len(await journal.list()) == 1


async def test_retention_age_keeps_active_and_unresolved_references(journal):
    old = datetime(2026, 1, 1, tzinfo=UTC)
    journal.clock = lambda: old
    await journal.accept(spec("expired"))
    await journal.finish("expired", OperationState.SUCCEEDED, writers_stopped=True)
    await journal.accept(spec("active"))
    await journal.accept(spec("recovery"))
    await journal.finish("recovery", OperationState.FAILED, writers_stopped=True,
                         recovery_refs=[RecoveryReference("restoration", "synthetic-retained")])
    journal.clock = lambda: old + timedelta(days=31)
    assert await journal.prune() == 1
    assert {record.operation_id for record in await journal.list()} == {"active", "recovery"}


@pytest.mark.parametrize("resource", [
    ResourceReference("world", "survival", None),
    ResourceReference("world", "survival", 0),
    ResourceReference("world", "survival", 12, "/etc"),
    ResourceReference("world", "survival", 12, "world/../../other"),
])
async def test_journal_rejects_unbound_or_unconfined_resources(journal, resource):
    with pytest.raises(ValueError):
        await journal.accept(replace(spec("invalid"), resources=(resource,)))
    assert await journal.list() == []


async def test_resource_identity_preserves_linux_filename_characters(journal):
    resource = ResourceReference("files", "长" * 200, 12, "world\\literal/" + "a" * 800)
    record = await journal.accept(replace(spec("linux-path"), resources=(resource,)))
    assert record.resources == (resource,)


async def test_large_raw_progress_or_secret_payload_cannot_enter_history(journal):
    secret = "synthetic-provider-secret-83"
    with pytest.raises(TypeError):
        OperationSpec(kind="restore", resources=(RESOURCE,), request_body={"password": secret})  # type: ignore[call-arg]
    await journal.accept(spec("bounded"))
    with pytest.raises(ValueError):
        await journal.phase("bounded", "progress-" + secret + ("x" * 200_000))
    with pytest.raises(ValueError):
        await journal.phase("bounded", "backup", recovery_refs=[RecoveryReference("snapshot", "https://credential:secret@host/repo")])
    async with journal.session_factory() as session:
        rows = (await session.execute(select(OperationJournalEntry.__table__))).mappings().all()
    assert secret not in json.dumps([dict(row) for row in rows], default=str)
    assert (await journal.get("bounded")).phase == "accepted"


async def test_reference_resolution_is_explicit_and_preserves_actor_evidence(journal):
    await journal.accept(spec("retained"))
    await journal.finish("retained", OperationState.INTERRUPTED, writers_stopped=False,
                         recovery_refs=[RecoveryReference("snapshot", "c" * 64)])
    record = await journal.resolve("retained", actor_id=9, writers_stopped=True)
    assert record.blocked_reason is None
    assert record.resolved_by == 9 and record.resolved_at is not None
    assert not record.recovery_refs[0].resolved
