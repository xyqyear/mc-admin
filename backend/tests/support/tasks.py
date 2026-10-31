"""Observe accepted API tasks on the test client's persistent event loop."""

import time
from typing import Literal

from fastapi.testclient import TestClient


def wait_task(
    client: TestClient, response, *, success: bool = True,
    expected_status: Literal["completed", "failed", "cancelled"] | None = None,
    timeout: float = 10,
) -> dict:
    assert response.status_code == 202, response.text
    task_id = response.json()["task_id"]
    authorization = response.request.headers.get("authorization")
    headers = {"Authorization": authorization} if authorization else {}
    expected = expected_status or ("completed" if success else "failed")
    prefix = "/api" if response.request.url.path.startswith("/api/") else ""
    deadline = time.monotonic() + timeout
    task = None
    while time.monotonic() < deadline:
        status = client.get(f"{prefix}/tasks/{task_id}", headers=headers)
        assert status.status_code == 200, status.text
        task = status.json()
        if task["status"] in {"completed", "failed", "cancelled"}:
            assert task["status"] == expected, task
            return task
        time.sleep(0.01)
    raise AssertionError(f"Task {task_id} did not settle within {timeout}s; last observation: {task}")


def task_result(client: TestClient, response) -> dict:
    return wait_task(client, response)["result"]
