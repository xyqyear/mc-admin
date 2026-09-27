"""Observe accepted API tasks on the test client's persistent event loop."""

import time

from fastapi.testclient import TestClient


def wait_task(client: TestClient, response, *, success: bool = True) -> dict:
    assert response.status_code == 202, response.text
    task_id = response.json()["task_id"]
    authorization = response.request.headers.get("authorization")
    headers = {"Authorization": authorization} if authorization else {}
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status = client.get(f"/tasks/{task_id}", headers=headers)
        assert status.status_code == 200, status.text
        task = status.json()
        if task["status"] in {"completed", "failed", "cancelled"}:
            assert task["status"] == ("completed" if success else "failed"), task
            return task
        time.sleep(0.01)
    raise AssertionError(f"Task {task_id} did not settle")


def task_result(client: TestClient, response) -> dict:
    return wait_task(client, response)["result"]
