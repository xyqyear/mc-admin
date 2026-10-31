import asyncio
from dataclasses import replace

from sqlalchemy import select

from app.self_check import tasks
from app.self_check.checks import CHECK_DEFINITIONS
from app.self_check.models import SelfCheckRun


async def test_running_check_exposes_current_findings_before_durable_completion(
    database, runtime_config, isolated_runtime,
):
    service = isolated_runtime.self_check_service
    first = CHECK_DEFINITIONS["dependency.binaries"]
    second = CHECK_DEFINITIONS["storage.server_directory_usage"]
    started = asyncio.Event()
    release = asyncio.Event()
    updates = []

    async def held_storage_check(context):
        started.set()
        await release.wait()
        return await second.function(context)

    service.definitions = {
        first.check_id: first,
        second.check_id: replace(second, function=held_storage_check),
    }
    service.check_ids = tuple(service.definitions)

    async def observe():
        async for update in tasks.self_check_task(73, None):
            updates.append(update)

    observer = asyncio.create_task(observe())
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        assert not observer.done()
        assert all(update.result is None for update in updates)
        details = updates[-1].progress_details
        assert updates[-1].progress == 50
        assert details is not None
        assert details["checking"] and details["check_id"] == second.check_id
        assert details["completed_checks"] == 1 and details["total_checks"] == 2
        assert details["findings"] and details["findings_total"] >= 1
        assert all(finding["check_id"] == first.check_id for finding in details["findings"])
        async with database.session_factory() as session:
            assert list(await session.scalars(select(SelfCheckRun))) == []
    finally:
        release.set()
        await asyncio.wait_for(observer, timeout=5)

    final = updates[-1]
    assert final.progress == 100 and final.result is not None
    async with database.session_factory() as session:
        run = (await session.scalars(select(SelfCheckRun))).one()
        assert run.id == final.result["id"]
        assert run.requested_by_user_id == 73 and run.finished_at is not None
