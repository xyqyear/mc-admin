import asyncio
import json
from datetime import UTC, datetime, time
from unittest.mock import AsyncMock, MagicMock

import httpx2 as httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.auth.models import UserRole
from app.auth.schemas import UserPublic
from app.cron.jobs.backup import BackupJobParams
from app.cron.jobs.restart import ServerRestartParams, restart_server_cronjob
from app.cron.manager import CronManager
from app.cron.models import CronJob, CronJobExecution, CronJobStatus, ExecutionStatus
from app.cron.restart_scheduler import RestartScheduler
from app.db.metadata import Base
from app.dependencies import get_current_user
from app.operations.journal import OperationJournal
from app.routers import cron as cron_routes
from app.routers.servers import restart_schedule as routes
from app.servers.models import Server, ServerStatus
from tests.support.runtime import set_runtime_resource


@pytest.fixture
async def schedules(isolated_runtime, monkeypatch):
    engine = isolated_runtime.database.engine
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = isolated_runtime.database.session_factory
    async with factory() as session:
        session.add_all([Server(server_id=name) for name in ("survival", "survival2")])
        await session.commit()
    monkeypatch.setattr("app.cron.manager.get_async_session", factory)
    manager = CronManager()
    manager.scheduler.start(paused=True)
    set_runtime_resource(monkeypatch, "cron_manager", manager)
    journal = OperationJournal(factory)
    await journal.initialize_changes()
    monkeypatch.setattr(isolated_runtime, "journal", journal)
    app = FastAPI()
    app.include_router(routes.router)
    app.include_router(cron_routes.router)
    app.dependency_overrides[get_current_user] = lambda: UserPublic(
        id=1, username="review-owner", role=UserRole.OWNER, created_at=datetime.now(UTC)
    )
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client, manager, factory
    finally:
        await manager.shutdown()


async def test_prefix_schedule_operations_preserve_other_server_and_custom_jobs(schedules):
    client, manager, factory = schedules
    for server in ("survival", "survival2"):
        response = await client.post(f"/servers/{server}/restart-schedule", json={"custom_cron": "0 6 1 1 *"})
        assert response.status_code == 200
    custom_id = await manager.create_cronjob(
        "restart_server", ServerRestartParams(server_id="survival"), "0 8 1 1 *", name="custom-survival"
    )
    async with factory() as db:
        rows = list((await db.execute(select(CronJob))).scalars())
        protected = {row.cronjob_id: (row.name, row.params_json, row.cron, row.status)
                     for row in rows if row.name != "restart-survival"}
    first = (await client.get("/servers/survival/restart-schedule")).json()
    second = (await client.get("/servers/survival2/restart-schedule")).json()
    assert first["cronjob_id"] != second["cronjob_id"]
    assert first["cronjob_id"] != custom_id
    for method, suffix, payload, expected in (
        ("POST", "", {"custom_cron": "0 9 1 1 *"}, "active"),
        ("POST", "/pause", None, "paused"),
        ("POST", "/resume", None, "active"),
        ("DELETE", "", None, "cancelled"),
        ("POST", "", {"custom_cron": "0 10 1 1 *"}, "active"),
    ):
        response = await client.request(method, "/servers/survival/restart-schedule" + suffix, json=payload)
        assert response.status_code == 200, response.text
        current = (await client.get("/servers/survival/restart-schedule")).json()
        assert current["cronjob_id"] == first["cronjob_id"]
        assert current["status"] == expected
        async with factory() as db:
            rows = list((await db.execute(select(CronJob))).scalars())
            assert {row.cronjob_id: (row.name, row.params_json, row.cron, row.status)
                    for row in rows if row.cronjob_id in protected} == protected


async def test_display_name_is_not_ownership_and_custom_canonical_name_remains_independent(schedules):
    client, manager, factory = schedules
    response = await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 6 * * *"})
    managed = response.json()["cronjob_id"]
    await manager.update_cronjob(managed, "restart_server", ServerRestartParams(server_id="survival"), "0 6 * * *", name="My schedule")
    custom = await manager.create_cronjob("restart_server", ServerRestartParams(server_id="survival"), "0 7 * * *", name="restart-survival")
    response = await client.get("/servers/survival/restart-schedule")
    assert response.json()["cronjob_id"] == managed
    assert response.json()["name"] == "My schedule"
    assert (await client.post("/servers/survival/restart-schedule/pause")).status_code == 200
    async with factory() as session:
        row = await session.scalar(select(CronJob).where(CronJob.cronjob_id == custom))
        assert row is not None and row.status == CronJobStatus.ACTIVE
        assert row.managed_purpose is None


async def test_slot_selection_excludes_only_current_managed_plan(schedules):
    from app.cron.restart_scheduler import RestartScheduler

    client, manager, _ = schedules
    assert (await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 6 * * *"})).status_code == 200
    await manager.create_cronjob("restart_server", ServerRestartParams(server_id="survival"), "5 6 * * *", name="restart-survival")
    assert await RestartScheduler(manager).get_restart_time_slots("survival") == {(6, 5)}


async def test_auto_schedule_persists_selected_slot_and_preserves_custom_cron(schedules, monkeypatch):
    client, manager, factory = schedules
    set_runtime_resource(monkeypatch, "restart_scheduler", RestartScheduler(manager, restart_start_time=time(6, 0)))
    custom_cron = "15 6 1 */2 1-5"
    created = await client.post("/servers/survival/restart-schedule", json={"custom_cron": custom_cron})
    assert created.status_code == 200 and created.json()["cron"] == custom_cron
    managed_id = created.json()["cronjob_id"]
    assert (await client.get("/servers/survival/restart-schedule")).json()["cron"] == custom_cron
    backup_id = await manager.create_cronjob("backup", BackupJobParams(enable_forget=False), "0 * * * *")
    await manager.pause_cronjob(backup_id)
    independent_id = await manager.create_cronjob(
        "restart_server", ServerRestartParams(server_id="survival"), "5 6 * * *", name="restart-survival",
    )
    await manager.pause_cronjob(independent_id)
    other_id = await manager.create_cronjob("restart_server", ServerRestartParams(server_id="survival2"), "10 6 * * *")
    async with factory() as session:
        original = await session.scalar(select(CronJob).where(CronJob.cronjob_id == managed_id))
        assert original is not None and original.cron == custom_cron
    for _ in range(2):
        response = await client.post("/servers/survival/restart-schedule", json={})
        assert response.status_code == 200
        assert response.json()["cronjob_id"] == managed_id
        assert response.json()["cron"] == "15 6 * * *" and response.json()["scheduled_time"] == "06:15"
        async with factory() as session:
            rows = {row.cronjob_id: row for row in await session.scalars(select(CronJob))}
            assert rows[managed_id].cron == "15 6 * * *" and rows[managed_id].managed_purpose == "restart"
            assert rows[backup_id].status == rows[independent_id].status == CronJobStatus.PAUSED
            assert rows[independent_id].cron == "5 6 * * *" and rows[independent_id].managed_purpose is None
            assert rows[other_id].cron == "10 6 * * *" and rows[other_id].status == CronJobStatus.ACTIVE


async def test_multiple_historical_plans_choose_one_without_mutating_history(schedules):
    client, manager, factory = schedules
    async with factory() as session:
        for identifier, target, state, purpose in (
            ("older-cancelled", "survival", CronJobStatus.CANCELLED, "restart"),
            ("oldest-paused", "survival", CronJobStatus.PAUSED, "restart"),
            ("newer-active", "survival", CronJobStatus.ACTIVE, "restart"),
            ("newest-cancelled", "survival", CronJobStatus.CANCELLED, "restart"),
            ("similar-target", "survival2", CronJobStatus.ACTIVE, "restart"),
            ("independent", "survival", CronJobStatus.ACTIVE, None),
        ):
            session.add(CronJob(
                cronjob_id=identifier, identifier="restart_server", name="restart-unrelated",
                cron="0 6 * * *", params_json=json.dumps({"server_id": target}),
                managed_purpose=purpose, status=state,
            ))
        session.add(CronJobExecution(
            cronjob_id="older-cancelled", execution_id="kept-history",
            started_at=datetime.now(UTC), status=ExecutionStatus.COMPLETED,
            messages_json='["原有历史"]',
        ))
        await session.commit()
        before = [(row.cronjob_id, row.name, row.params_json, row.status, row.updated_at)
                  for row in await session.scalars(select(CronJob).order_by(CronJob.id))]
    for _ in range(2):
        response = await client.get("/servers/survival/restart-schedule")
        assert response.status_code == 200
        assert response.json()["cronjob_id"] == "oldest-paused"
        assert response.json()["name"] == "restart-unrelated"
    async with factory() as session:
        after = [(row.cronjob_id, row.name, row.params_json, row.status, row.updated_at)
                 for row in await session.scalars(select(CronJob).order_by(CronJob.id))]
        assert before == after
    await manager._recover_cronjobs_from_database()
    assert all(manager.scheduler.get_job(job) is not None for job in ("newer-active", "similar-target", "independent"))
    assert manager.scheduler.get_job("oldest-paused") is None
    await manager.cancel_cronjob("oldest-paused")
    assert (await client.get("/servers/survival/restart-schedule")).json()["cronjob_id"] == "newer-active"
    await manager.cancel_cronjob("newer-active")
    current = (await client.get("/servers/survival/restart-schedule")).json()
    assert current["cronjob_id"] == "newest-cancelled" and current["status"] == "cancelled"
    assert manager.scheduler.get_job("newest-cancelled") is None
    response = await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 8 * * *"})
    assert response.status_code == 200 and response.json()["cronjob_id"] == "newest-cancelled"
    async with factory() as session:
        rows = {row.cronjob_id: row for row in await session.scalars(select(CronJob))}
        assert rows["newest-cancelled"].status == CronJobStatus.ACTIVE
        assert all(rows[job].status == CronJobStatus.CANCELLED for job in ("older-cancelled", "oldest-paused", "newer-active"))
        assert rows["independent"].status == rows["similar-target"].status == CronJobStatus.ACTIVE
        history = await session.scalar(select(CronJobExecution).where(CronJobExecution.execution_id == "kept-history"))
        assert history is not None and history.messages_json == '["原有历史"]'


@pytest.mark.parametrize("method", ["PUT", "POST"])
async def test_managed_plan_can_change_name_and_parameter_target(schedules, method):
    client, _, _ = schedules
    response = await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 6 * * *"})
    job_id = response.json()["cronjob_id"]
    url = f"/cron/{job_id}" if method == "PUT" else "/cron/"
    response = await client.request(method, url, json={
        "identifier": "restart_server", "params": {"server_id": "survival2"},
        "cron": "0 9 * * *", "cronjob_id": job_id, "name": "restart-survival",
    })
    assert response.status_code == 200
    assert (await client.get("/servers/survival/restart-schedule")).json() is None
    current = (await client.get("/servers/survival2/restart-schedule")).json()
    assert current["cronjob_id"] == job_id and current["name"] == "restart-survival"
    detail = (await client.get(f"/cron/{job_id}")).json()
    assert detail["params"] == {"server_id": "survival2"} and detail["managed_purpose"] == "restart"
    assert "managed_server_generation" not in detail and "managed_binding_issue" not in detail


@pytest.mark.parametrize("method", ["PUT", "POST"])
async def test_managed_plan_keeps_restart_type(schedules, method):
    client, _, _ = schedules
    job_id = (await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 6 * * *"})).json()["cronjob_id"]
    response = await client.request(method, f"/cron/{job_id}" if method == "PUT" else "/cron/", json={
        "identifier": "backup", "params": {"enable_forget": False}, "cron": "0 8 * * *", "cronjob_id": job_id,
    })
    assert response.status_code == 409
    detail = (await client.get(f"/cron/{job_id}")).json()
    assert detail["identifier"] == "restart_server" and detail["params"] == {"server_id": "survival"}


async def test_invalid_historical_params_remain_readable_and_can_be_repaired(schedules):
    client, manager, factory = schedules
    job_id = (await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 6 * * *"})).json()["cronjob_id"]
    await manager.pause_cronjob(job_id)
    async with factory() as session:
        job = await session.scalar(select(CronJob).where(CronJob.cronjob_id == job_id))
        assert job is not None
        job.params_json = "invalid historical JSON"
        await session.commit()
    detail = (await client.get(f"/cron/{job_id}")).json()
    assert detail["registration_error"] == "定时任务配置无效，请修改后重新启用"
    assert detail["params"] == {} and detail["status"] == "paused"
    assert (await client.post(f"/cron/{job_id}/resume")).status_code == 400
    assert (await client.put(f"/cron/{job_id}", json={
        "identifier": "restart_server", "params": {"server_id": "survival"}, "cron": "0 6 * * *",
    })).status_code == 200
    assert (await client.post(f"/cron/{job_id}/resume")).status_code == 200
    assert (await client.get("/servers/survival/restart-schedule")).json()["cronjob_id"] == job_id


async def test_managed_schedule_concurrent_creates_return_same_plan(schedules):
    _, manager, factory = schedules
    results = await asyncio.gather(*(
        manager.create_managed_restart_schedule("survival", ServerRestartParams(server_id="survival"), "0 6 * * *", "restart-survival")
        for _ in range(6)
    ))
    assert len(set(results)) == 1
    async with factory() as session:
        rows = list(await session.scalars(select(CronJob)))
        assert len(rows) == 1 and rows[0].managed_purpose == "restart"
    await manager.pause_cronjob(results[0])
    retained = await manager.create_managed_restart_schedule("survival", ServerRestartParams(server_id="survival"), "0 9 * * *", "new name")
    assert retained == results[0]
    async with factory() as session:
        row = await session.scalar(select(CronJob))
        assert row is not None and row.cron == "0 6 * * *" and row.status == CronJobStatus.PAUSED
        assert row.name == "restart-survival"


async def test_next_restart_uses_current_same_named_instance(schedules, monkeypatch):
    from app.servers import commands

    client, manager, factory = schedules
    job_id = (await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 6 * * *"})).json()["cronjob_id"]
    async with factory() as session:
        old = await session.scalar(select(Server).where(Server.server_id == "survival"))
        assert old is not None
        old_id = old.id
        old.status = ServerStatus.REMOVED
        await session.flush()
        current = Server(server_id="survival")
        session.add(current)
        await session.commit()
        new_id = current.id
        assert new_id != old_id
    assert (await client.get("/servers/survival/restart-schedule")).json()["cronjob_id"] == job_id
    project = commands.get_settings().server_path / "survival"
    project.mkdir()
    (project / "docker-compose.yml").write_text("services: {}\n")
    instance = MagicMock(exists=AsyncMock(return_value=True), running=AsyncMock(return_value=True))
    docker = MagicMock()
    docker.get_instance.return_value = instance
    set_runtime_resource(monkeypatch, "docker_mc_manager", docker)
    run = AsyncMock()
    monkeypatch.setattr(commands.ServerCommands, "_run", run)
    await manager._execute_cronjob_wrapper(job_id, "restart_server", ServerRestartParams(server_id="survival"), restart_server_cronjob)
    assert run.await_args is not None
    reference, action, actor_id = run.await_args.args
    assert reference.generation == new_id and reference.server_id == "survival"
    assert action == "restart" and actor_id is None
    history = await manager.get_execution_history(job_id)
    assert history[0].status.value == "completed"


@pytest.mark.parametrize("mutation", ["pause", "cancel"])
async def test_paused_or_cancelled_plan_does_not_execute(schedules, mutation):
    client, manager, _ = schedules
    job_id = (await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 6 * * *"})).json()["cronjob_id"]
    await getattr(manager, f"{mutation}_cronjob")(job_id)
    job = AsyncMock()
    await manager._execute_cronjob_wrapper(job_id, "restart_server", ServerRestartParams(server_id="survival"), job)
    job.assert_not_awaited()
    assert (await manager.get_execution_history(job_id))[0].status.value == "skipped"


async def test_recovery_registers_valid_targets_without_historical_name_checks(schedules):
    client, manager, factory = schedules
    job_id = (await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 6 * * *"})).json()["cronjob_id"]
    async with factory() as session:
        job = await session.scalar(select(CronJob).where(CronJob.cronjob_id == job_id))
        assert job is not None
        job.name = "restart-an-unrelated-name"
        old = await session.scalar(select(Server).where(Server.server_id == "survival"))
        assert old is not None
        old.status = ServerStatus.REMOVED
        await session.flush()
        session.add(Server(server_id="survival"))
        await session.commit()
    manager.scheduler.remove_all_jobs()
    await manager._recover_cronjobs_from_database()
    assert manager.scheduler.get_job(job_id) is not None
    current = (await client.get("/servers/survival/restart-schedule")).json()
    assert current["cronjob_id"] == job_id and current["name"] == "restart-an-unrelated-name"


async def test_restart_revalidates_current_reference_after_acquiring_maintenance(schedules, monkeypatch):
    from contextlib import asynccontextmanager

    from app.cron.types import ExecutionContext
    from app.servers import commands
    from app.world.locks import get_server_operation_lock

    _, _, factory = schedules
    async with factory() as session:
        generation = await session.scalar(select(Server.id).where(Server.server_id == "survival"))
        assert generation is not None

    @asynccontextmanager
    async def acquire(*args, **kwargs):
        async with factory() as session:
            old = await session.get(Server, generation)
            assert old is not None
            old.status = ServerStatus.REMOVED
            await session.flush()
            session.add(Server(server_id="survival"))
            await session.commit()
        yield True

    monkeypatch.setattr(get_server_operation_lock(), "try_acquire", acquire)
    project = commands.get_settings().server_path / "survival"
    project.mkdir()
    (project / "docker-compose.yml").write_text("services: {}\n")
    docker = MagicMock()
    set_runtime_resource(monkeypatch, "docker_mc_manager", docker)
    context = ExecutionContext(
        cronjob_id="old", execution_id="old-execution", identifier="restart_server",
        params=ServerRestartParams(server_id="survival"), started_at=datetime.now(UTC),
    )
    await restart_server_cronjob(context)
    assert context.status.value == "skipped"
    assert any("实例已变更" in message for message in context.messages)
    docker.get_instance.assert_not_called()


@pytest.mark.parametrize("state", ["missing", "missing_project", "missing_container", "stopped"])
async def test_missing_or_stopped_target_records_skipped_restart(schedules, monkeypatch, state):
    from app.servers import commands

    client, manager, factory = schedules
    job_id = (await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 6 * * *"})).json()["cronjob_id"]
    if state == "missing":
        async with factory() as session:
            old = await session.scalar(select(Server).where(Server.server_id == "survival"))
            assert old is not None
            old.status = ServerStatus.REMOVED
            await session.commit()
    elif state != "missing_project":
        project = commands.get_settings().server_path / "survival"
        project.mkdir()
        (project / "docker-compose.yml").write_text("services: {}\n")
    instance = MagicMock(exists=AsyncMock(return_value=state != "missing_container"), running=AsyncMock(return_value=False), restart=AsyncMock())
    docker = MagicMock()
    docker.get_instance.return_value = instance
    set_runtime_resource(monkeypatch, "docker_mc_manager", docker)
    await manager._execute_cronjob_wrapper(job_id, "restart_server", ServerRestartParams(server_id="survival"), restart_server_cronjob)
    [history] = await manager.get_execution_history(job_id)
    assert history.status.value == "skipped" and history.ended_at is not None and history.messages
    instance.restart.assert_not_awaited()
    if state in ("missing", "missing_project"):
        docker.get_instance.assert_not_called()


async def test_deactivation_cancels_only_active_exact_parameter_targets(schedules):
    from app.servers.lifecycle.primitives import cancel_restart_cronjobs_for_server

    client, manager, factory = schedules
    managed = (await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 6 * * *"})).json()["cronjob_id"]
    independent = await manager.create_cronjob("restart_server", ServerRestartParams(server_id="survival"), "0 7 * * *", name="restart-survival2")
    similar = await manager.create_cronjob("restart_server", ServerRestartParams(server_id="survival2"), "0 8 * * *", name="restart-survival")
    paused = await manager.create_cronjob("restart_server", ServerRestartParams(server_id="survival"), "0 9 * * *")
    invalid = await manager.create_cronjob("restart_server", ServerRestartParams(server_id="survival2"), "0 10 * * *")
    await manager.pause_cronjob(paused)
    async with factory() as session:
        job = await session.scalar(select(CronJob).where(CronJob.cronjob_id == invalid))
        assert job is not None
        job.params_json = "malformed historical JSON"
        await session.commit()
    async with factory() as session:
        cancelled = await cancel_restart_cronjobs_for_server(session, "survival")
    assert set(cancelled) == {managed, independent}
    async with factory() as session:
        rows = {row.cronjob_id: row for row in await session.scalars(select(CronJob))}
        assert rows[managed].status == rows[independent].status == CronJobStatus.CANCELLED
        assert rows[similar].status == rows[invalid].status == CronJobStatus.ACTIVE
        assert rows[paused].status == CronJobStatus.PAUSED
