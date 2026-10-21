"""Schedule changes cannot transfer a caller's operation to later cron work."""

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.cron import crud
from app.cron.manager import CronManager
from app.cron.models import ExecutionStatus
from app.operations.context import bind_execution, current_execution, record_phase
from app.operations.execution import operation_scope
from app.operations.journal import OperationJournal
from app.operations.journal_types import OperationState
from app.runtime_resources import current_runtime
from app.self_check.checks import CHECK_DEFINITIONS
from app.self_check.constants import SCHEDULED_TRIGGER
from app.self_check.job import SelfCheckJobParams, self_check_cronjob
from app.self_check.models import SelfCheckRun


async def test_schedule_change_does_not_contaminate_existing_timer_chain(database, isolated_runtime):
    runtime = isolated_runtime
    runtime.journal = OperationJournal(database.session_factory)
    manager = CronManager()
    observations = asyncio.Queue()
    changed = asyncio.Event()

    async def existing_job():
        await observations.put((current_runtime(), current_execution()))

    async def new_job():
        await observations.put((current_runtime(), current_execution()))
        changed.set()

    manager.scheduler.start()
    try:
        manager.scheduler.add_job(existing_job, "interval", seconds=0.05, id="existing")
        async with asyncio.timeout(5):
            assert await observations.get() == (runtime, None)
            manager.scheduler.pause()
            async with operation_scope("server_create", []) as parent:
                assert parent is not None
                manager.scheduler.add_job(new_job, "date", run_date=datetime.now(UTC))
                manager.scheduler.resume()
                await changed.wait()
                assert current_execution() is parent
            # Observe the new job and repeated old-job ticks after the caller has reset its context.
            for _ in range(3):
                assert await observations.get() == (runtime, None)
    finally:
        await manager.shutdown()
        await asyncio.sleep(0)


@pytest.mark.parametrize("fail", [False, True])
async def test_cron_entry_owns_outcome_independently_of_completed_parent(
    database, runtime_config, isolated_runtime, fail,
):
    runtime = isolated_runtime
    journal = OperationJournal(database.session_factory)
    runtime.journal = journal
    service = runtime.self_check_service
    service.definitions = {"dependency.binaries": CHECK_DEFINITIONS["dependency.binaries"]}
    service.check_ids = tuple(service.definitions)
    params = SelfCheckJobParams()
    async with database.session_factory() as session:
        await crud.create_cronjob(
            session, cronjob_id="scheduled-check", identifier="self_check", name="定时巡检",
            cron="0 0 * * *", params_json=params.model_dump_json(),
        )
    async with operation_scope("server_create", []) as parent:
        assert parent is not None
    before = await journal.get(parent.operation_id)
    assert before is not None and before.state is OperationState.SUCCEEDED

    async def run(context):
        await self_check_cronjob(context)
        if fail:
            await record_phase("publishing_diagnostics")
            raise RuntimeError("巡检发布失败")

    manager = CronManager()
    try:
        with bind_execution(parent):
            await manager._execute_cronjob_wrapper("scheduled-check", "self_check", params, run)
            assert current_execution() is parent
    finally:
        await manager.shutdown()
    history = await manager.get_execution_history("scheduled-check")
    assert len(history) == 1
    assert history[0].status is (ExecutionStatus.FAILED if fail else ExecutionStatus.COMPLETED)
    assert history[0].ended_at is not None
    records = await OperationJournal(database.session_factory).list()
    assert len(records) == 2
    own = next(record for record in records if record.operation_id != parent.operation_id)
    assert own.kind == "cron_self_check" and own.origin == "cron"
    assert own.legacy_id == history[0].execution_id
    assert own.state is (OperationState.FAILED if fail else OperationState.SUCCEEDED)
    assert own.writers_stopped
    assert await journal.get(parent.operation_id) == before
    async with database.session_factory() as session:
        runs = list(await session.scalars(select(SelfCheckRun)))
        assert len(runs) == 1 and runs[0].trigger == SCHEDULED_TRIGGER
        assert runs[0].finished_at is not None


async def test_committed_cron_success_survives_late_cancellation(database, isolated_runtime):
    from app.operations.execution import settle_execution

    journal = OperationJournal(database.session_factory)
    isolated_runtime.journal = journal
    params = SelfCheckJobParams()
    async with database.session_factory() as session:
        await crud.create_cronjob(
            session, cronjob_id="committed-check", identifier="self_check", name="已完成巡检",
            cron="0 0 * * *", params_json=params.model_dump_json(),
        )

    async def committed_job(context):
        operation = current_execution()
        assert operation is not None
        await record_phase("diagnostics_committed")
        await settle_execution(operation, OperationState.SUCCEEDED)
        raise asyncio.CancelledError

    manager = CronManager()
    try:
        with pytest.raises(asyncio.CancelledError):
            await manager._execute_cronjob_wrapper("committed-check", "self_check", params, committed_job)
    finally:
        await manager.shutdown()
    history = await manager.get_execution_history("committed-check")
    assert len(history) == 1 and history[0].status is ExecutionStatus.COMPLETED
    records = await journal.list()
    assert len(records) == 1
    assert records[0].origin == "cron" and records[0].legacy_id == history[0].execution_id
    assert records[0].state is OperationState.SUCCEEDED and records[0].writers_stopped
