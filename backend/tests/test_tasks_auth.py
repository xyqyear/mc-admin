import asyncio

import pytest
from httpx2 import ASGITransport, AsyncClient

from app.auth.models import UserRole
from app.auth.session import AUTH_COOKIE_NAME, CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.background_tasks import TaskProgress, TaskType
from app.config import get_settings
from app.main import app
from tests.support.auth import PASSWORD, create_account

REQUESTS = [
    ("GET", "/api/tasks"),
    ("GET", "/api/tasks?active_only=true"),
    ("GET", "/api/tasks/auth-running"),
    ("POST", "/api/tasks/auth-running/cancel"),
    ("DELETE", "/api/tasks/auth-finished"),
    ("DELETE", "/api/tasks"),
]
MUTATIONS = [request for request in REQUESTS if request[0] != "GET"]


@pytest.fixture
async def task_api(database, isolated_runtime):
    manager = isolated_runtime.task_manager
    started, cleaned = asyncio.Event(), asyncio.Event()

    async def running():
        try:
            yield TaskProgress(progress=10, result={"test": "retained"})
            started.set()
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    async def completed():
        yield TaskProgress(progress=100, result={"large": ["payload"]})

    async def failed():
        yield TaskProgress(progress=20)
        raise RuntimeError("synthetic failure")

    try:
        await manager.submit(TaskType.ARCHIVE_CREATE, "completed", completed(), task_id="auth-finished").awaitable
        await manager.submit(TaskType.ARCHIVE_CREATE, "failed", failed(), task_id="auth-retained").awaitable
        manager.submit(TaskType.ARCHIVE_CREATE, "running", running(), task_id="auth-running")
        await asyncio.wait_for(started.wait(), 5)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, manager, cleaned
    finally:
        await manager.shutdown()


def task_state(manager):
    return {task.task_id: (task.model_dump(), task.cancel_requested) for task in manager.get_all_tasks()}


async def authenticate(client, sessions, role):
    if role == "master":
        client.headers["Authorization"] = f"Bearer {get_settings().master_token}"
        return
    user = await create_account(sessions, username=f"task-{role}", role=UserRole(role))
    response = await client.post("/api/auth/token", data={"username": user.username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    client.headers[CSRF_HEADER_NAME] = client.cookies[CSRF_COOKIE_NAME]


@pytest.mark.parametrize("method,path", REQUESTS)
@pytest.mark.parametrize("session", ["anonymous", "invalid"])
async def test_task_routes_reject_unauthenticated_requests_without_changes(task_api, method, path, session):
    client, manager, cleaned = task_api
    if session == "invalid":
        client.cookies.set(AUTH_COOKIE_NAME, "invalid-session", path="/api")
    before = task_state(manager)
    response = await client.request(method, path)
    assert response.status_code == 401
    assert task_state(manager) == before
    assert not cleaned.is_set()


@pytest.mark.parametrize("role", ["admin", "owner", "master"])
async def test_authenticated_users_can_read_cancel_delete_and_clear_tasks(task_api, db_session_factory, role):
    client, manager, cleaned = task_api
    await authenticate(client, db_session_factory, role)
    listing = await client.get("/api/tasks")
    assert listing.status_code == 200
    assert listing.json()["total"] == 3
    assert all("result" not in row for row in listing.json()["tasks"])
    detail = await client.get("/api/tasks/auth-finished")
    assert detail.json()["result"] == {"large": ["payload"]}
    active = await client.get("/api/tasks?active_only=true")
    assert [row["task_id"] for row in active.json()["tasks"]] == ["auth-running"]
    future = manager.get_future("auth-running")
    assert future is not None
    cancelled = await client.post("/api/tasks/auth-running/cancel")
    assert cancelled.status_code == 200 and cancelled.json() == {"success": True}
    await asyncio.wait_for(future, 5)
    assert cleaned.is_set()
    terminal = await client.get("/api/tasks/auth-running")
    assert terminal.json()["status"] == "cancelled"
    assert (await client.delete("/api/tasks/auth-finished")).status_code == 200
    assert (await client.get("/api/tasks/auth-finished")).status_code == 404
    cleared = await client.delete("/api/tasks")
    assert cleared.status_code == 200 and cleared.json() == {"cleared": 2}
    assert (await client.get("/api/tasks")).json()["total"] == 0


@pytest.mark.parametrize("method,path", MUTATIONS)
@pytest.mark.parametrize("role", ["admin", "owner"])
async def test_authenticated_task_mutations_require_csrf_without_changes(task_api, db_session_factory, method, path, role):
    client, manager, cleaned = task_api
    await authenticate(client, db_session_factory, role)
    del client.headers[CSRF_HEADER_NAME]
    before = task_state(manager)
    response = await client.request(method, path)
    assert response.status_code == 403
    assert task_state(manager) == before
    assert not cleaned.is_set()
