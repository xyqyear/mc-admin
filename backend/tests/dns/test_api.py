import asyncio

import pytest
from httpx2 import ASGITransport, AsyncClient

from app.auth.models import UserRole
from app.auth.session import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.main import app
from app.operations.journal import OperationJournal
from app.operations.models import OperationJournalEntry
from tests.support.auth import PASSWORD, create_account
from tests.support.runtime import set_runtime_resource


@pytest.fixture
async def dns_api(connectivity, isolated_runtime, db_session_factory, runtime_config, monkeypatch):
    isolated_runtime.journal = OperationJournal(db_session_factory)
    account = await create_account(db_session_factory, username="dns-admin", role=UserRole.ADMIN)
    connectivity.manager._configuration = lambda: runtime_config.dns
    set_runtime_resource(monkeypatch, "dns_manager", connectivity.manager)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/auth/token", data={"username": account.username, "password": PASSWORD})
            assert response.status_code == 200, response.text
            client.headers[CSRF_HEADER_NAME] = client.cookies[CSRF_COOKIE_NAME]
            yield client
    finally:
        await isolated_runtime.task_manager.shutdown()


async def test_dns_status_and_reads_observe_real_plan_without_writing(dns_api, connectivity):
    status = await dns_api.get("/api/dns/status")
    assert status.status_code == 200
    assert status.json()["state"] == "pending"
    assert {row["sub_domain"] for row in status.json()["dns_diff"]["records_to_add"]} == {"*.mc", "_minecraft._tcp.survival.mc"}
    assert status.json()["router_diff"]["routes_to_add"] == {"survival.mc.example.com": "localhost:25565"}
    assert (await dns_api.get("/api/dns/records")).json() == []
    assert (await dns_api.get("/api/dns/routes")).json() == {}
    assert (await dns_api.get("/api/dns/enabled")).json() == {"enabled": True}
    assert connectivity.provider.calls == [] and connectivity.router.calls == []


async def test_dns_acceptance_precedes_remote_completion_and_reads_settled_state(dns_api, connectivity, isolated_runtime, db_session_factory):
    connectivity.provider.started = asyncio.Event()
    connectivity.provider.release = asyncio.Event()
    try:
        accepted = await dns_api.post("/api/dns/update")
        assert accepted.status_code == 202, accepted.text
        identity = accepted.json()["task_id"]
        await asyncio.wait_for(connectivity.provider.started.wait(), 5)
        pending = await dns_api.get(f"/api/tasks/{identity}")
        assert pending.json()["status"] == "running"
        duplicate = await dns_api.post("/api/dns/update")
        assert duplicate.status_code == 423
        assert duplicate.json()["detail"]["task_id"] == identity
        future = isolated_runtime.task_manager.get_future(identity)
        assert future is not None
        connectivity.provider.release.set()
        assert (await asyncio.wait_for(future, 5)).success
        task = await dns_api.get(f"/api/tasks/{identity}")
        assert task.json()["status"] == "completed" and task.json()["result"]["success"]
        assert task.json()["task_type"] == "dns_update"
        async with db_session_factory() as session:
            operation = await session.get(OperationJournalEntry, identity)
            assert operation is not None
            assert operation.kind == "dns_update" and operation.state == "succeeded"
            assert operation.writers_stopped and operation.ended_at is not None
        status = await dns_api.get("/api/dns/status")
        assert status.json()["state"] == "ready"
        records = (await dns_api.get("/api/dns/records")).json()
        assert {row["sub_domain"] for row in records} == {"*.mc", "_minecraft._tcp.survival.mc"}
        assert all(row["record_id"] for row in records)
        assert (await dns_api.get("/api/dns/routes")).json() == {"survival.mc.example.com": "localhost:25565"}
    finally:
        connectivity.provider.release.set()


async def test_dns_failure_is_terminal_and_retry_preserves_unrelated_progress(dns_api, connectivity, isolated_runtime):
    connectivity.provider.unavailable = True
    response = await dns_api.post("/api/dns/update")
    assert response.status_code == 202
    future = isolated_runtime.task_manager.get_future(response.json()["task_id"])
    assert future is not None
    assert not (await asyncio.wait_for(future, 5)).success
    task = (await dns_api.get(f"/api/tasks/{response.json()['task_id']}")).json()
    assert task["status"] == "failed"
    assert "synthetic-provider-secret" not in str(task)
    assert connectivity.router.routes == {"survival.mc.example.com": "localhost:25565"}
    status = (await dns_api.get("/api/dns/status")).json()
    assert status["state"] == "degraded" and not status["dns_known"] and status["router_known"]
    assert status["dns_diff"] is None
    connectivity.provider.unavailable = False
    retry = await dns_api.post("/api/dns/update")
    assert retry.status_code == 202
    future = isolated_runtime.task_manager.get_future(retry.json()["task_id"])
    assert future is not None and (await asyncio.wait_for(future, 5)).success
    assert (await dns_api.get("/api/dns/status")).json()["state"] == "ready"


@pytest.mark.parametrize("path,adapter", [("records", "provider"), ("routes", "router")])
async def test_dns_read_failure_returns_safe_error(dns_api, connectivity, path, adapter):
    getattr(connectivity, adapter).unavailable = True
    response = await dns_api.get(f"/api/dns/{path}")
    assert response.status_code == 500
    assert response.json()["detail"] == "服务器内部错误，请稍后重试"
    assert "secret" not in response.text


async def test_disabled_dns_rejects_operations_without_remote_effects(dns_api, connectivity, isolated_runtime):
    config = connectivity.configuration.model_copy(update={"enabled": False})
    await isolated_runtime.config_manager.update_config("dns", config.model_dump())
    assert (await dns_api.get("/api/dns/enabled")).json() == {"enabled": False}
    for path in ("status", "records", "routes"):
        assert (await dns_api.get(f"/api/dns/{path}")).status_code == 503
    assert (await dns_api.post("/api/dns/update")).status_code == 503
    assert connectivity.provider.calls == [] and connectivity.router.calls == []
    assert isolated_runtime.task_manager.get_all_tasks() == []


async def test_dns_endpoints_require_identity_and_mutations_require_csrf(dns_api, connectivity, isolated_runtime):
    del dns_api.headers[CSRF_HEADER_NAME]
    assert (await dns_api.post("/api/dns/update")).status_code == 403
    dns_api.cookies.clear()
    for path in ("status", "records", "routes", "enabled"):
        assert (await dns_api.get(f"/api/dns/{path}")).status_code == 401
    assert (await dns_api.post("/api/dns/update")).status_code == 401
    assert connectivity.provider.calls == [] and connectivity.router.calls == []
    assert isolated_runtime.task_manager.get_all_tasks() == []
