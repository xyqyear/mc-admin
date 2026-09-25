import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx2 as httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.auth.schemas import UserPublic
from app.cron import crud
from app.cron.manager import CronManager
from app.cron.models import CronJob, CronJobExecution, CronJobStatus, ExecutionStatus
from app.cron.registry import CronRegistry
from app.db.metadata import Base
from app.dependencies import get_current_user
from app.dynamic_config.schemas import BaseConfigSchema
from app.routers import cron as routes
from tests.support.runtime import set_runtime_resource


class Params(BaseConfigSchema):
    value: int = 1


@pytest.fixture
async def scheduling(isolated_runtime, monkeypatch):
    runtime = isolated_runtime
    async with runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    registry = CronRegistry()
    calls = AsyncMock()
    registry.register_func(calls, Params, identifier="probe")
    set_runtime_resource(monkeypatch, 'cron_registry', registry)
    manager = CronManager()
    set_runtime_resource(monkeypatch, 'cron_manager', manager)
    set_runtime_resource(monkeypatch, 'cron_registry', registry)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: UserPublic(id=1, username="owner", created_at=datetime.now(UTC))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield SimpleNamespace(manager=manager, registry=registry, calls=calls, sessions=runtime.database.session_factory, client=client)
    finally:
        await manager.shutdown()
        await asyncio.sleep(0)


async def create(env, job_id="configured"):
    return await env.manager.create_cronjob("probe", Params(), "0 0 1 1 *", cronjob_id=job_id)


async def test_registration_failure_is_visible_and_existing_resume_repairs(scheduling, monkeypatch):
    env = scheduling
    await env.manager.initialize()
    original = env.manager.scheduler.add_job

    def fail(*args, **kwargs):
        raise RuntimeError("adapter token must stay private")

    monkeypatch.setattr(env.manager.scheduler, "add_job", fail)
    await create(env)
    response = await env.client.get("/cron/configured")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "active" and body["registration_status"] == "failed"
    assert body["registration_error"] == "调度器注册失败，请重新启用任务"
    assert "token" not in response.text
    env.calls.assert_not_awaited()
    monkeypatch.setattr(env.manager.scheduler, "add_job", original)
    assert (await env.client.post("/cron/configured/resume")).status_code == 200
    body = (await env.client.get("/cron/configured")).json()
    assert body["registration_status"] == "registered" and body["registration_error"] is None
    assert (await env.client.post("/cron/configured/resume")).status_code == 409


@pytest.mark.parametrize("mutation", ["pause", "cancel", "update"])
async def test_queued_old_trigger_cannot_execute_changed_configuration(scheduling, mutation):
    env = scheduling
    await env.manager.initialize()
    await create(env)
    queued = env.manager.scheduler.get_job("configured")
    assert queued is not None
    if mutation == "update":
        await env.manager.update_cronjob("configured", "probe", Params(value=2), "0 1 1 1 *")
    else:
        await getattr(env.manager, f"{mutation}_cronjob")("configured")
    await queued.func(*queued.args, **queued.kwargs)
    env.calls.assert_not_awaited()
    [record] = await env.manager.get_execution_history("configured")
    assert record.status is ExecutionStatus.SKIPPED and record.ended_at is not None
    assert record.duration_ms is not None and record.messages
    config = await env.manager.get_cronjob_config("configured")
    assert config is not None and config.execution_count == 1


async def test_invalid_persisted_jobs_remain_visible_and_do_not_prevent_valid_registration(scheduling):
    env = scheduling
    async with env.sessions() as session:
        for job_id, identifier, params in [("unknown", "removed-provider", '{"value":8}'), ("invalid", "probe", '{"value":"bad"}')]:
            await crud.create_cronjob(session, cronjob_id=job_id, identifier=identifier, name=job_id, cron="0 0 1 1 *", params_json=params)
    await create(env)
    assert (await env.client.get("/cron/configured")).json()["registration_status"] == "pending"
    await env.manager.initialize()
    rows = {row["cronjob_id"]: row for row in (await env.client.get("/cron/")).json()}
    assert set(rows) == {"configured", "unknown", "invalid"}
    assert rows["configured"]["registration_status"] == "registered"
    assert rows["unknown"]["registration_status"] == rows["invalid"]["registration_status"] == "failed"
    assert rows["unknown"]["params"] == {"value": 8}
    assert rows["invalid"]["params"] == {"value": "bad"}
    assert (await env.client.get("/cron/unknown")).status_code == 200
    async with env.sessions() as session:
        invalid = await crud.get_cronjob(session, "invalid")
        assert invalid is not None and invalid.params_json == '{"value":"bad"}'


async def test_scheduler_remains_paused_until_startup_reconciliation_completes(scheduling, monkeypatch):
    env = scheduling
    entered, release = asyncio.Event(), asyncio.Event()
    original = env.manager._ensure_system_cronjobs

    async def ensure():
        entered.set()
        await release.wait()
        await original()

    monkeypatch.setattr(env.manager, "_ensure_system_cronjobs", ensure)
    startup = asyncio.create_task(env.manager.initialize())
    try:
        await entered.wait()
        assert env.manager.scheduler.state == 2
        env.calls.assert_not_awaited()
        release.set()
        await startup
        assert env.manager.scheduler.state == 1
    finally:
        release.set()
        await startup


async def test_running_is_durable_before_command_and_terminal_count_is_idempotent(scheduling):
    env = scheduling
    await create(env)
    entered, finish = asyncio.Event(), asyncio.Event()

    async def command(context):
        entered.set()
        await finish.wait()

    worker = asyncio.create_task(env.manager._execute_cronjob_wrapper("configured", "probe", Params(), command))
    try:
        await entered.wait()
        [running] = await env.manager.get_execution_history("configured")
        assert running.status is ExecutionStatus.RUNNING and running.ended_at is None
        config = await env.manager.get_cronjob_config("configured")
        assert config is not None and config.execution_count == 0
        finish.set()
        await worker
        [completed] = await env.manager.get_execution_history("configured")
        assert completed.execution_id == running.execution_id and completed.status is ExecutionStatus.COMPLETED
        async with env.sessions() as session:
            await crud.finish_execution_record(session, {"execution_id": completed.execution_id, "status": ExecutionStatus.FAILED})
        [retained] = await env.manager.get_execution_history("configured")
        assert retained.status is ExecutionStatus.COMPLETED and retained.ended_at == completed.ended_at
        config = await env.manager.get_cronjob_config("configured")
        assert config is not None and config.execution_count == 1
    finally:
        finish.set()
        await worker


async def test_startup_interruption_preserves_history_and_counts_once(scheduling):
    env = scheduling
    await create(env)
    started = datetime.now(UTC) - timedelta(seconds=5)
    async with env.sessions() as session:
        await crud.create_execution_record(session, {
            "execution_id": "interrupted", "cronjob_id": "configured", "started_at": started,
            "status": ExecutionStatus.RUNNING, "messages_json": json.dumps(["原有进度"]),
        })
        await crud.interrupt_running_executions(session)
        await crud.interrupt_running_executions(session)
    [history] = await env.manager.get_execution_history("configured")
    assert history.execution_id == "interrupted" and history.started_at == started
    assert history.status is ExecutionStatus.FAILED and history.ended_at is not None
    assert history.duration_ms is not None and history.duration_ms >= 5000
    assert history.messages == ["原有进度", "应用重启前的定时任务已中断，请查看操作历史"]
    config = await env.manager.get_cronjob_config("configured")
    assert config is not None and config.status is CronJobStatus.ACTIVE and config.execution_count == 1
    env.calls.assert_not_awaited()


async def test_resume_invalid_paused_config_does_not_change_desired_status(scheduling):
    env = scheduling
    await create(env)
    await env.manager.pause_cronjob("configured")
    async with env.sessions() as session:
        await crud.update_cronjob(session, "configured", params_json='{"value":"bad"}')
    with pytest.raises(ValueError):
        await env.manager.resume_cronjob("configured")
    async with env.sessions() as session:
        row = await session.scalar(select(CronJob).where(CronJob.cronjob_id == "configured"))
        assert row is not None and row.status is CronJobStatus.PAUSED
        assert list(await session.scalars(select(CronJobExecution))) == []


async def test_fatal_startup_coordination_failure_stops_scheduler(scheduling, monkeypatch):
    env = scheduling
    await create(env)

    async def fail():
        raise ValueError("system registration collision")

    monkeypatch.setattr(env.manager, "_ensure_system_cronjobs", fail)
    with pytest.raises(ValueError, match="collision"):
        await env.manager.initialize()
    await asyncio.sleep(0)
    assert not env.manager.scheduler.running and not env.manager._initialized
    env.calls.assert_not_awaited()
    assert (await env.client.get("/cron/configured")).json()["registration_status"] == "pending"
