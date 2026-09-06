from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.auth.session import (
    AUTH_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    create_session_token,
)
from app.background_tasks.manager import BackgroundTaskManager
from app.background_tasks.models import BackgroundTask
from app.background_tasks.types import TaskStatus, TaskType
from app.config import settings
from app.main import app
from app.models import UserPublic, UserRole
from app.routers import tasks as task_router

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
def task_api(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, BackgroundTaskManager]]:
    manager = BackgroundTaskManager()
    for task_id, status in (
        ("auth-running", TaskStatus.RUNNING),
        ("auth-finished", TaskStatus.COMPLETED),
        ("auth-retained", TaskStatus.FAILED),
    ):
        manager._tasks[task_id] = BackgroundTask(
            task_id=task_id,
            task_type=TaskType.ARCHIVE_CREATE,
            name=task_id,
            status=status,
            result={"test": "retained"},
        )
    monkeypatch.setattr(task_router, "task_manager", manager)
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client, manager
    finally:
        client.close()


def task_state(manager: BackgroundTaskManager):
    return {
        task.task_id: (task.model_dump(), task.cancel_requested)
        for task in manager.get_all_tasks()
    }


def authenticate(client: TestClient, role: str) -> None:
    if role == "master":
        client.headers["Authorization"] = f"Bearer {settings.master_token}"
        return
    user = UserPublic(
        id=42,
        username=f"task-{role}",
        role=UserRole(role),
        created_at=datetime.now(UTC),
    )
    token, csrf = create_session_token(user)
    client.cookies.set(AUTH_COOKIE_NAME, token, path="/api")
    client.cookies.set(CSRF_COOKIE_NAME, csrf, path="/")
    client.headers[CSRF_HEADER_NAME] = csrf


@pytest.mark.parametrize("method,path", REQUESTS)
@pytest.mark.parametrize("session", ["anonymous", "invalid"])
def test_task_routes_reject_unauthenticated_requests_without_changes(
    task_api: tuple[TestClient, BackgroundTaskManager],
    method: str,
    path: str,
    session: str,
):
    client, manager = task_api
    if session == "invalid":
        client.cookies.set(AUTH_COOKIE_NAME, "invalid-session", path="/api")
    before = task_state(manager)

    response = client.request(method, path)

    assert response.status_code == 401
    assert task_state(manager) == before


@pytest.mark.parametrize("role", ["admin", "owner", "master"])
def test_authenticated_users_can_read_cancel_delete_and_clear_tasks(
    task_api: tuple[TestClient, BackgroundTaskManager], role: str
):
    client, manager = task_api
    authenticate(client, role)

    listing = client.get("/api/tasks")
    assert listing.status_code == 200
    assert listing.json()["total"] == 3
    assert all("result" not in row for row in listing.json()["tasks"])
    active = client.get("/api/tasks?active_only=true")
    assert active.status_code == 200
    assert [row["task_id"] for row in active.json()["tasks"]] == ["auth-running"]
    detail = client.get("/api/tasks/auth-running")
    assert detail.status_code == 200
    assert detail.json()["result"] == {"test": "retained"}

    cancelled = client.post("/api/tasks/auth-running/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json() == {"success": True}
    running = manager.get_task("auth-running")
    assert running is not None and running.cancel_requested
    assert client.delete("/api/tasks/auth-finished").status_code == 200
    assert manager.get_task("auth-finished") is None
    cleared = client.delete("/api/tasks")
    assert cleared.status_code == 200
    assert cleared.json() == {"cleared": 1}
    assert [task.task_id for task in manager.get_all_tasks()] == ["auth-running"]


@pytest.mark.parametrize("method,path", MUTATIONS)
@pytest.mark.parametrize("role", ["admin", "owner"])
def test_authenticated_task_mutations_require_csrf_without_changes(
    task_api: tuple[TestClient, BackgroundTaskManager],
    method: str,
    path: str,
    role: str,
):
    client, manager = task_api
    authenticate(client, role)
    del client.headers[CSRF_HEADER_NAME]
    before = task_state(manager)

    response = client.request(method, path)

    assert response.status_code == 403
    assert task_state(manager) == before
