from datetime import UTC, datetime

import httpx2 as httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.models import UserRole
from app.auth.schemas import UserPublic
from app.cron.jobs.restart import ServerRestartParams
from app.cron.manager import CronManager
from app.cron.models import CronJob, CronJobStatus
from app.db.metadata import Base
from app.dependencies import get_current_user
from app.routers import cron as cron_routes
from app.routers.servers import restart_schedule as routes
from app.servers.models import Server, ServerStatus
from tests.support.runtime import set_runtime_resource


@pytest.fixture
async def schedules(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'schedules.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all([Server(server_id=name) for name in ("survival", "survival2")])
        await session.commit()
    monkeypatch.setattr("app.cron.manager.get_async_session", factory)
    manager = CronManager()
    manager.scheduler.start(paused=True)
    set_runtime_resource(monkeypatch, 'cron_manager', manager)
    set_runtime_resource(monkeypatch, 'cron_manager', manager)
    set_runtime_resource(monkeypatch, 'cron_manager', manager)
    app = FastAPI()
    app.include_router(routes.router)
    app.include_router(cron_routes.router)
    app.dependency_overrides[get_current_user] = lambda: UserPublic(
        id=1, username="review-owner", role=UserRole.OWNER, created_at=datetime.now(UTC)
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, manager, factory
    await manager.shutdown()
    await engine.dispose()


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


@pytest.mark.parametrize("ambiguous", ["duplicate", "mismatched-params"])
async def test_ambiguous_schedule_is_reported_without_mutation(schedules, ambiguous):
    client, manager, factory = schedules
    await manager.create_cronjob(
        "restart_server", ServerRestartParams(server_id="survival"), "0 6 1 1 *", name="restart-survival"
    )
    if ambiguous == "duplicate":
        await manager.create_cronjob(
            "restart_server", ServerRestartParams(server_id="survival"), "0 7 1 1 *", name="restart-survival"
        )
    async with factory() as db:
        for job in (await db.execute(select(CronJob))).scalars():
            job.managed_purpose = "restart"
            job.managed_binding_issue = "duplicate_candidates" if ambiguous == "duplicate" else "name_params_mismatch"
            if ambiguous == "mismatched-params":
                job.params_json = '{"server_id":"different"}'
        await db.commit()
    async with factory() as db:
        before = [(job.cronjob_id, job.params_json, job.cron, job.status) for job in (await db.execute(select(CronJob))).scalars()]
    for method, suffix in (("GET", ""), ("POST", ""), ("POST", "/pause"), ("POST", "/resume"), ("DELETE", "")):
        response = await client.request(method, "/servers/survival/restart-schedule" + suffix,
                                        json={"custom_cron": "0 9 1 1 *"} if method == "POST" and not suffix else None)
        assert response.status_code == 409, response.text
    async with factory() as db:
        after = [(job.cronjob_id, job.params_json, job.cron, job.status) for job in (await db.execute(select(CronJob))).scalars()]
    assert after == before


async def test_display_name_is_not_ownership_and_custom_canonical_name_remains_independent(schedules):
    client, manager, factory = schedules
    response = await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 6 * * *"})
    managed = response.json()["cronjob_id"]
    await manager.update_cronjob(managed, "restart_server", ServerRestartParams(server_id="survival"), "0 6 * * *", name="My schedule")
    custom = await manager.create_cronjob("restart_server", ServerRestartParams(server_id="survival"), "0 7 * * *", name="restart-survival")
    response = await client.get("/servers/survival/restart-schedule")
    assert response.json()["cronjob_id"] == managed
    assert (await client.post("/servers/survival/restart-schedule/pause")).status_code == 200
    async with factory() as session:
        row = await session.scalar(select(CronJob).where(CronJob.cronjob_id == custom))
        assert row is not None and row.status == CronJobStatus.ACTIVE
        assert row.managed_purpose is None and row.managed_server_generation is None


async def test_recreated_name_does_not_inherit_or_execute_old_plan(schedules):
    from unittest.mock import AsyncMock

    client, manager, factory = schedules
    response = await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 6 * * *"})
    old_job = response.json()["cronjob_id"]
    await manager.pause_cronjob(old_job)
    async with factory() as session:
        old = await session.scalar(select(Server).where(Server.server_id == "survival"))
        assert old is not None
        old.status = ServerStatus.REMOVED
        await session.flush()
        current = Server(server_id="survival")
        session.add(current)
        await session.commit()
        new_generation = current.id
    assert (await client.get("/servers/survival/restart-schedule")).json() is None
    response = await client.post(f"/cron/{old_job}/resume")
    assert response.status_code == 409, response.text
    response = await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 8 * * *"})
    new_job = response.json()["cronjob_id"]
    assert new_job != old_job
    detail = (await client.get(f"/cron/{new_job}")).json()
    assert detail["managed_server_generation"] == new_generation
    assert detail["managed_purpose"] == "restart"
    function = AsyncMock()
    await manager._execute_cronjob_wrapper(old_job, "restart_server", ServerRestartParams(server_id="survival"), function)
    function.assert_not_awaited()
    history = await manager.get_execution_history(old_job)
    assert history[0].status.value == "skipped"
    assert any("同名新实例" in message for message in history[0].messages)


async def test_managed_plan_cannot_be_retargeted_by_generic_cron_api(schedules):
    client, _, _ = schedules
    response = await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 6 * * *"})
    job_id = response.json()["cronjob_id"]
    for method, url in (("PUT", f"/cron/{job_id}"), ("POST", "/cron/")):
        response = await client.request(method, url, json={
            "identifier": "restart_server", "params": {"server_id": "survival2"},
            "cron": "0 9 * * *", "cronjob_id": job_id,
        })
        assert response.status_code == 409, response.text
    detail = (await client.get(f"/cron/{job_id}")).json()
    assert detail["params"] == {"server_id": "survival"}
    assert detail["cron"] == "0 6 * * *"


async def test_ambiguous_invalid_params_remain_readable_and_cancel_resolves_block(schedules):
    client, manager, factory = schedules
    job_id = await manager.create_cronjob("restart_server", ServerRestartParams(server_id="survival"), "0 6 * * *", name="restart-survival")
    async with factory() as session:
        job = await session.scalar(select(CronJob).where(CronJob.cronjob_id == job_id))
        assert job is not None
        job.params_json = "invalid historical JSON"
        job.managed_purpose = "restart"
        job.managed_binding_issue = "invalid_params"
        await session.commit()
    response = await client.get(f"/cron/{job_id}")
    assert response.status_code == 200
    assert response.json()["managed_binding_issue"] == "历史任务参数无效，无法确定归属"
    response = await client.get("/cron/")
    assert response.status_code == 200 and any(row["cronjob_id"] == job_id for row in response.json())
    assert (await client.get("/servers/survival/restart-schedule")).status_code == 409
    assert (await client.delete(f"/cron/{job_id}")).status_code == 200
    assert (await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 8 * * *"})).status_code == 200
    async with factory() as session:
        job = await session.scalar(select(CronJob).where(CronJob.cronjob_id == job_id))
        assert job is not None and job.params_json == "invalid historical JSON"
        assert job.managed_binding_issue == "invalid_params"


async def test_managed_schedule_uniqueness_under_concurrent_creates(schedules):
    import asyncio

    _, manager, factory = schedules
    results = await asyncio.gather(*(
        manager.create_managed_restart_schedule("survival", ServerRestartParams(server_id="survival"), "0 6 * * *", "restart-survival")
        for _ in range(2)
    ), return_exceptions=True)
    assert sum(isinstance(result, str) for result in results) == 1
    assert sum(isinstance(result, ValueError) for result in results) == 1
    async with factory() as session:
        rows = list(await session.scalars(select(CronJob)))
        assert len(rows) == 1 and rows[0].managed_server_generation is not None


async def test_slot_selection_excludes_only_current_managed_plan(schedules):
    from app.cron.restart_scheduler import RestartScheduler

    client, manager, _ = schedules
    assert (await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 6 * * *"})).status_code == 200
    await manager.create_cronjob("restart_server", ServerRestartParams(server_id="survival"), "5 6 * * *", name="restart-survival")
    assert await RestartScheduler(manager).get_restart_time_slots("survival") == {(6, 5)}


async def test_restart_revalidates_generation_after_acquiring_maintenance(schedules, monkeypatch):
    from contextlib import asynccontextmanager
    from unittest.mock import MagicMock

    from app.cron.jobs import restart
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
    monkeypatch.setattr(commands, "get_async_session", factory)
    docker = MagicMock()
    set_runtime_resource(monkeypatch, 'docker_mc_manager', docker)
    context = ExecutionContext(
        cronjob_id="old", execution_id="old-execution", identifier="restart_server",
        params=ServerRestartParams(server_id="survival"), started_at=datetime.now(UTC),
        managed_server_generation=generation,
    )
    await restart.restart_server_cronjob(context)
    assert context.status.value == "skipped"
    assert any("同名新实例" in message for message in context.messages)
    docker.get_instance.assert_not_called()


async def test_recovery_does_not_register_ambiguous_or_retired_plan(schedules):
    client, manager, factory = schedules
    response = await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 6 * * *"})
    bound_id = response.json()["cronjob_id"]
    ambiguous_id = await manager.create_cronjob("restart_server", ServerRestartParams(server_id="survival2"), "0 7 * * *", name="restart-survival2")
    async with factory() as session:
        old = await session.scalar(select(Server).where(Server.server_id == "survival"))
        assert old is not None
        old.status = ServerStatus.REMOVED
        job = await session.scalar(select(CronJob).where(CronJob.cronjob_id == ambiguous_id))
        assert job is not None
        job.managed_purpose = "restart"
        job.managed_binding_issue = "generation_uncertain"
        await session.commit()
    manager.scheduler.remove_all_jobs()
    await manager._recover_cronjobs_from_database()
    assert manager.scheduler.get_job(bound_id) is None
    assert manager.scheduler.get_job(ambiguous_id) is None
    async with factory() as session:
        assert all(job.status == CronJobStatus.ACTIVE for job in await session.scalars(select(CronJob)))


async def test_deactivation_finds_only_current_binding_and_matching_independent_jobs(schedules):
    from app.cron.crud import get_active_restart_cronjobs_for_server

    client, manager, factory = schedules
    old_id = (await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 6 * * *"})).json()["cronjob_id"]
    independent = await manager.create_cronjob("restart_server", ServerRestartParams(server_id="survival"), "0 7 * * *", name="custom")
    other = await manager.create_cronjob("restart_server", ServerRestartParams(server_id="survival2"), "0 8 * * *", name="restart-survival2")
    async with factory() as session:
        old = await session.scalar(select(Server).where(Server.server_id == "survival"))
        assert old is not None
        old.status = ServerStatus.REMOVED
        await session.flush()
        session.add(Server(server_id="survival"))
        invalid = await session.scalar(select(CronJob).where(CronJob.cronjob_id == other))
        assert invalid is not None
        invalid.params_json = "malformed historical JSON"
        invalid.managed_purpose = "restart"
        invalid.managed_binding_issue = "invalid_params"
        await session.commit()
    new_id = (await client.post("/servers/survival/restart-schedule", json={"custom_cron": "0 9 * * *"})).json()["cronjob_id"]
    async with factory() as session:
        found = await get_active_restart_cronjobs_for_server(session, "survival")
        assert {job.cronjob_id for job in found} == {new_id, independent}
        assert (await session.scalar(select(CronJob.status).where(CronJob.cronjob_id == old_id))) == CronJobStatus.ACTIVE
        assert await get_active_restart_cronjobs_for_server(session, "survival2") == []
