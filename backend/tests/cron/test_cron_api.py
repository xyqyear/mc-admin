"""Cron job management REST API tests via TestClient."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app
from app.models import Base

from .test_cron_manager import test_cron_manager, test_cron_registry


@pytest.fixture(scope="function")
async def test_db():
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()

    database_url = f"sqlite+aiosqlite:///{temp_db.name}"
    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    import app.cron.manager as manager_module
    import app.db.database as db_module

    original_db_session = db_module.AsyncSessionLocal

    db_module.AsyncSessionLocal = TestSessionLocal

    def get_test_session():
        return TestSessionLocal()

    original_get_session = manager_module.get_async_session
    manager_module.get_async_session = get_test_session

    import app.routers.cron as cron_router_module

    original_cron_manager = cron_router_module.cron_manager
    original_cron_registry = cron_router_module.cron_registry

    cron_router_module.cron_manager = test_cron_manager
    cron_router_module.cron_registry = test_cron_registry

    await test_cron_manager.initialize()

    yield TestSessionLocal

    await test_cron_manager.shutdown()

    db_module.AsyncSessionLocal = original_db_session
    manager_module.get_async_session = original_get_session
    cron_router_module.cron_manager = original_cron_manager
    cron_router_module.cron_registry = original_cron_registry

    await engine.dispose()
    Path(temp_db.name).unlink(missing_ok=True)


@pytest.fixture
def client():
    with patch("app.dependencies.settings") as mock_settings:
        mock_settings.master_token = "test_master_token"
        client = TestClient(app, raise_server_exceptions=False)
        yield client


@pytest.fixture
async def authenticated_headers():
    return {"Authorization": "Bearer test_master_token"}


class TestCronJobAPI:
    def test_list_registered_cronjobs(self, test_db, client, authenticated_headers):
        response = client.get("/api/cron/registered", headers=authenticated_headers)

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        assert len(data) >= 1

        test_cronjob = next(
            (cronjob for cronjob in data if cronjob["identifier"] == "test_cronjob"),
            None,
        )
        assert test_cronjob is not None

        assert test_cronjob["description"] == "Simple test cron job"
        assert "parameter_schema" in test_cronjob
        assert isinstance(test_cronjob["parameter_schema"], dict)

        schema = test_cronjob["parameter_schema"]
        assert "properties" in schema
        assert "message" in schema["properties"]
        assert "delay_seconds" in schema["properties"]

    def test_create_cronjob_success(self, test_db, client, authenticated_headers):
        cronjob_data = {
            "identifier": "test_cronjob",
            "name": "API Test CronJob",
            "cron": "0 0 * * *",
            "params": {"message": "API created cronjob", "delay_seconds": 5},
        }

        response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert "cronjob_id" in data
        assert "message" in data
        assert data["message"] == "CronJob created successfully"

        created_cronjob_id = data["cronjob_id"]
        assert created_cronjob_id.startswith("test_cronjob_")

    def test_create_cronjob_with_custom_id(
        self, test_db, client, authenticated_headers
    ):
        custom_cronjob_id = "my_custom_api_cronjob"

        cronjob_data = {
            "identifier": "test_cronjob",
            "cronjob_id": custom_cronjob_id,
            "name": "Custom ID API CronJob",
            "cron": "*/5 * * * *",
            "params": {"message": "Custom ID cronjob", "delay_seconds": 0},
        }

        response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["cronjob_id"] == custom_cronjob_id

    def test_create_cronjob_invalid_identifier(
        self, test_db, client, authenticated_headers
    ):
        cronjob_data = {
            "identifier": "nonexistent_cronjob",
            "cron": "0 0 * * *",
            "params": {},
        }

        response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )

        assert response.status_code == 400
        assert "not registered" in response.json()["detail"]

    def test_create_cronjob_invalid_params(
        self, test_db, client, authenticated_headers
    ):
        cronjob_data = {
            "identifier": "test_cronjob",
            "cron": "0 0 * * *",
            "params": {
                "message": "Valid message",
                "delay_seconds": "invalid_number",
            },
        }

        response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )

        assert response.status_code == 400
        assert "Invalid parameters" in response.json()["detail"]

    def test_get_cronjob_success(self, test_db, client, authenticated_headers):
        cronjob_data = {
            "identifier": "test_cronjob",
            "name": "Get Test CronJob",
            "cron": "0 12 * * *",
            "second": "30",
            "params": {"message": "Get cronjob test", "delay_seconds": 10},
        }

        create_response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )
        cronjob_id = create_response.json()["cronjob_id"]

        response = client.get(f"/api/cron/{cronjob_id}", headers=authenticated_headers)

        assert response.status_code == 200
        data = response.json()

        assert data["cronjob_id"] == cronjob_id
        assert data["identifier"] == "test_cronjob"
        assert data["name"] == "Get Test CronJob"
        assert data["cron"] == "0 12 * * *"
        assert data["second"] == "30"
        assert data["status"] == "active"
        assert data["params"]["message"] == "Get cronjob test"
        assert data["params"]["delay_seconds"] == 10
        assert "created_at" in data
        assert "updated_at" in data
        assert "execution_count" in data

    def test_get_cronjob_not_found(self, test_db, client, authenticated_headers):
        response = client.get(
            "/api/cron/nonexistent_cronjob", headers=authenticated_headers
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_pause_cronjob(self, test_db, client, authenticated_headers):
        cronjob_data = {
            "identifier": "test_cronjob",
            "name": "Pause Test CronJob",
            "cron": "* * * * *",
            "params": {"message": "Pause test", "delay_seconds": 0},
        }

        create_response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )
        cronjob_id = create_response.json()["cronjob_id"]

        response = client.post(
            f"/api/cron/{cronjob_id}/pause", headers=authenticated_headers
        )

        assert response.status_code == 200
        assert "paused successfully" in response.json()["message"]

        get_response = client.get(
            f"/api/cron/{cronjob_id}", headers=authenticated_headers
        )
        assert get_response.json()["status"] == "paused"

    def test_resume_cronjob(self, test_db, client, authenticated_headers):
        cronjob_data = {
            "identifier": "test_cronjob",
            "name": "Resume Test CronJob",
            "cron": "0 0 * * *",
            "params": {"message": "Resume test", "delay_seconds": 0},
        }

        create_response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )
        cronjob_id = create_response.json()["cronjob_id"]

        client.post(f"/api/cron/{cronjob_id}/pause", headers=authenticated_headers)

        response = client.post(
            f"/api/cron/{cronjob_id}/resume", headers=authenticated_headers
        )

        assert response.status_code == 200
        assert "resumed successfully" in response.json()["message"]

        get_response = client.get(
            f"/api/cron/{cronjob_id}", headers=authenticated_headers
        )
        assert get_response.json()["status"] == "active"

    def test_cancel_cronjob(self, test_db, client, authenticated_headers):
        cronjob_data = {
            "identifier": "test_cronjob",
            "name": "Cancel Test CronJob",
            "cron": "0 0 * * *",
            "params": {"message": "Cancel test", "delay_seconds": 0},
        }

        create_response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )
        cronjob_id = create_response.json()["cronjob_id"]

        response = client.delete(
            f"/api/cron/{cronjob_id}", headers=authenticated_headers
        )

        assert response.status_code == 200
        assert "cancelled successfully" in response.json()["message"]

        get_response = client.get(
            f"/api/cron/{cronjob_id}", headers=authenticated_headers
        )
        assert get_response.json()["status"] == "cancelled"

    def test_get_cronjob_executions_empty(self, test_db, client, authenticated_headers):
        cronjob_data = {
            "identifier": "test_cronjob",
            "name": "Execution History Test",
            "cron": "0 0 1 1 *",
            "params": {"message": "History test", "delay_seconds": 0},
        }

        create_response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )
        cronjob_id = create_response.json()["cronjob_id"]

        response = client.get(
            f"/api/cron/{cronjob_id}/executions", headers=authenticated_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_cronjob_executions_with_limit(
        self, test_db, client, authenticated_headers
    ):
        cronjob_data = {
            "identifier": "test_cronjob",
            "name": "Execution Limit Test",
            "cron": "0 0 1 1 *",
            "params": {"message": "Limit test", "delay_seconds": 0},
        }

        create_response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )
        cronjob_id = create_response.json()["cronjob_id"]

        response = client.get(
            f"/api/cron/{cronjob_id}/executions?limit=10", headers=authenticated_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10

    def test_api_error_handling(self, test_db, client, authenticated_headers):
        nonexistent_cronjob_id = "nonexistent_cronjob_id"

        test_cases = [
            ("GET", f"/api/cron/{nonexistent_cronjob_id}", 404),
            ("POST", f"/api/cron/{nonexistent_cronjob_id}/pause", 500),
            ("POST", f"/api/cron/{nonexistent_cronjob_id}/resume", 500),
            ("DELETE", f"/api/cron/{nonexistent_cronjob_id}", 500),
            ("GET", f"/api/cron/{nonexistent_cronjob_id}/executions", 500),
        ]

        for method, endpoint, expected_status in test_cases:
            if method == "GET":
                response = client.get(endpoint, headers=authenticated_headers)
            elif method == "POST":
                response = client.post(endpoint, headers=authenticated_headers)
            elif method == "DELETE":
                response = client.delete(endpoint, headers=authenticated_headers)
            else:
                continue

            assert response.status_code == expected_status, (
                f"{method} {endpoint} should return {expected_status}"
            )

    def test_create_cronjob_with_second_field(
        self, test_db, client, authenticated_headers
    ):
        cronjob_data = {
            "identifier": "test_cronjob",
            "name": "Second Field Test",
            "cron": "* * * * *",
            "second": "*/10",
            "params": {"message": "Second field test", "delay_seconds": 0},
        }

        response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )

        assert response.status_code == 200
        cronjob_id = response.json()["cronjob_id"]

        get_response = client.get(
            f"/api/cron/{cronjob_id}", headers=authenticated_headers
        )
        assert get_response.json()["second"] == "*/10"

    def test_comprehensive_cronjob_lifecycle_via_api(
        self, test_db, client, authenticated_headers
    ):
        cronjob_data = {
            "identifier": "test_cronjob",
            "cronjob_id": "lifecycle_test_cronjob",
            "name": "Lifecycle Test CronJob",
            "cron": "*/30 * * * *",
            "params": {"message": "Lifecycle test cronjob", "delay_seconds": 1},
        }

        create_response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )
        assert create_response.status_code == 200

        cronjob_id = "lifecycle_test_cronjob"

        get_response = client.get(
            f"/api/cron/{cronjob_id}", headers=authenticated_headers
        )
        assert get_response.status_code == 200
        cronjob_details = get_response.json()
        assert cronjob_details["status"] == "active"

        pause_response = client.post(
            f"/api/cron/{cronjob_id}/pause", headers=authenticated_headers
        )
        assert pause_response.status_code == 200

        get_response = client.get(
            f"/api/cron/{cronjob_id}", headers=authenticated_headers
        )
        assert get_response.json()["status"] == "paused"

        resume_response = client.post(
            f"/api/cron/{cronjob_id}/resume", headers=authenticated_headers
        )
        assert resume_response.status_code == 200

        get_response = client.get(
            f"/api/cron/{cronjob_id}", headers=authenticated_headers
        )
        assert get_response.json()["status"] == "active"

        executions_response = client.get(
            f"/api/cron/{cronjob_id}/executions", headers=authenticated_headers
        )
        assert executions_response.status_code == 200

        cancel_response = client.delete(
            f"/api/cron/{cronjob_id}", headers=authenticated_headers
        )
        assert cancel_response.status_code == 200

        get_response = client.get(
            f"/api/cron/{cronjob_id}", headers=authenticated_headers
        )
        assert get_response.json()["status"] == "cancelled"

        # Re-creating with the same id recovers the cancelled job.
        recovery_response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )
        assert recovery_response.status_code == 200

        get_response = client.get(
            f"/api/cron/{cronjob_id}", headers=authenticated_headers
        )
        assert get_response.json()["status"] == "active"

    def test_list_cronjobs_with_filters(self, test_db, client, authenticated_headers):
        response1 = client.post(
            "/api/cron/",
            json={
                "identifier": "test_cronjob",
                "params": {},
                "cron": "0 0 * * *",
                "name": "Test Job 1",
            },
            headers=authenticated_headers,
        )
        if response1.status_code != 200:
            print(f"Response status: {response1.status_code}")
            print(f"Response body: {response1.text}")
        assert response1.status_code == 200
        cronjob_id1 = response1.json()["cronjob_id"]

        response2 = client.post(
            "/api/cron/",
            json={
                "identifier": "test_cronjob",
                "params": {},
                "cron": "0 1 * * *",
                "name": "Test Job 2",
            },
            headers=authenticated_headers,
        )
        assert response2.status_code == 200
        cronjob_id2 = response2.json()["cronjob_id"]

        response3 = client.post(
            "/api/cron/",
            json={
                "identifier": "test_cronjob",
                "params": {},
                "cron": "0 2 * * *",
                "name": "Test Job 3",
            },
            headers=authenticated_headers,
        )
        assert response3.status_code == 200
        cronjob_id3 = response3.json()["cronjob_id"]

        pause_response = client.post(
            f"/api/cron/{cronjob_id2}/pause", headers=authenticated_headers
        )
        assert pause_response.status_code == 200

        cancel_response = client.delete(
            f"/api/cron/{cronjob_id3}", headers=authenticated_headers
        )
        assert cancel_response.status_code == 200

        response = client.get("/api/cron/", headers=authenticated_headers)
        assert response.status_code == 200
        jobs = response.json()
        assert len(jobs) == 2
        job_ids = [job["cronjob_id"] for job in jobs]
        assert cronjob_id1 in job_ids
        assert cronjob_id2 in job_ids
        assert cronjob_id3 not in job_ids

        response = client.get(
            "/api/cron/?identifier=test_cronjob", headers=authenticated_headers
        )
        assert response.status_code == 200
        jobs = response.json()
        assert len(jobs) == 2
        for job in jobs:
            assert job["identifier"] == "test_cronjob"

        response = client.get("/api/cron/?status=active", headers=authenticated_headers)
        assert response.status_code == 200
        jobs = response.json()
        assert len(jobs) == 1
        assert jobs[0]["cronjob_id"] == cronjob_id1
        assert jobs[0]["status"] == "active"

        response = client.get("/api/cron/?status=paused", headers=authenticated_headers)
        assert response.status_code == 200
        jobs = response.json()
        assert len(jobs) == 1
        assert jobs[0]["cronjob_id"] == cronjob_id2
        assert jobs[0]["status"] == "paused"

        response = client.get(
            "/api/cron/?status=cancelled", headers=authenticated_headers
        )
        assert response.status_code == 200
        jobs = response.json()
        assert len(jobs) == 1
        assert jobs[0]["cronjob_id"] == cronjob_id3
        assert jobs[0]["status"] == "cancelled"

        response = client.get(
            "/api/cron/?status=active&status=cancelled", headers=authenticated_headers
        )
        assert response.status_code == 200
        jobs = response.json()
        assert len(jobs) == 2
        job_ids = [job["cronjob_id"] for job in jobs]
        assert cronjob_id1 in job_ids
        assert cronjob_id3 in job_ids
        assert cronjob_id2 not in job_ids

        response = client.get(
            "/api/cron/?identifier=test_cronjob&status=active",
            headers=authenticated_headers,
        )
        assert response.status_code == 200
        jobs = response.json()
        assert len(jobs) == 1
        assert jobs[0]["cronjob_id"] == cronjob_id1
        assert jobs[0]["identifier"] == "test_cronjob"
        assert jobs[0]["status"] == "active"

    def test_resume_cronjob_status_validation(
        self, test_db, client, authenticated_headers
    ):
        response = client.post(
            "/api/cron/",
            json={
                "identifier": "test_cronjob",
                "params": {},
                "cron": "0 0 * * *",
                "name": "Test Job",
            },
            headers=authenticated_headers,
        )
        assert response.status_code == 200
        cronjob_id = response.json()["cronjob_id"]

        # Resuming an already-active job should fail.
        resume_response = client.post(
            f"/api/cron/{cronjob_id}/resume", headers=authenticated_headers
        )
        assert resume_response.status_code == 500
        assert "already active" in resume_response.json()["detail"]

        pause_response = client.post(
            f"/api/cron/{cronjob_id}/pause", headers=authenticated_headers
        )
        assert pause_response.status_code == 200

        resume_response = client.post(
            f"/api/cron/{cronjob_id}/resume", headers=authenticated_headers
        )
        assert resume_response.status_code == 200

        cancel_response = client.delete(
            f"/api/cron/{cronjob_id}", headers=authenticated_headers
        )
        assert cancel_response.status_code == 200

        resume_response = client.post(
            f"/api/cron/{cronjob_id}/resume", headers=authenticated_headers
        )
        assert resume_response.status_code == 200

        get_response = client.get(
            f"/api/cron/{cronjob_id}", headers=authenticated_headers
        )
        assert get_response.status_code == 200
        assert get_response.json()["status"] == "active"

    def test_update_cronjob_success(self, test_db, client, authenticated_headers):
        create_data = {
            "identifier": "test_cronjob",
            "name": "Original Test Job",
            "cron": "0 0 * * *",
            "params": {"message": "Original message", "delay_seconds": 5},
        }

        create_response = client.post(
            "/api/cron/", json=create_data, headers=authenticated_headers
        )
        assert create_response.status_code == 200
        cronjob_id = create_response.json()["cronjob_id"]

        update_data = {
            "identifier": "test_cronjob",
            "cron": "0 12 * * *",
            "second": "30",
            "params": {"message": "Updated message", "delay_seconds": 10},
        }

        update_response = client.put(
            f"/api/cron/{cronjob_id}", json=update_data, headers=authenticated_headers
        )
        assert update_response.status_code == 200
        assert "updated successfully" in update_response.json()["message"]

        get_response = client.get(
            f"/api/cron/{cronjob_id}", headers=authenticated_headers
        )
        assert get_response.status_code == 200

        updated_job = get_response.json()
        assert updated_job["cronjob_id"] == cronjob_id
        assert updated_job["identifier"] == "test_cronjob"
        assert updated_job["name"] == "Original Test Job"
        assert updated_job["cron"] == "0 12 * * *"
        assert updated_job["second"] == "30"
        assert updated_job["params"]["message"] == "Updated message"
        assert updated_job["params"]["delay_seconds"] == 10
        assert updated_job["status"] == "active"

    def test_update_cronjob_not_found(self, test_db, client, authenticated_headers):
        update_data = {
            "identifier": "test_cronjob",
            "cron": "0 12 * * *",
            "params": {"message": "Test", "delay_seconds": 5},
        }

        response = client.put(
            "/api/cron/nonexistent_cronjob",
            json=update_data,
            headers=authenticated_headers,
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_update_cronjob_invalid_identifier(
        self, test_db, client, authenticated_headers
    ):
        create_data = {
            "identifier": "test_cronjob",
            "name": "Test Job",
            "cron": "0 0 * * *",
            "params": {"message": "Test", "delay_seconds": 5},
        }

        create_response = client.post(
            "/api/cron/", json=create_data, headers=authenticated_headers
        )
        cronjob_id = create_response.json()["cronjob_id"]

        update_data = {
            "identifier": "nonexistent_cronjob",
            "cron": "0 12 * * *",
            "params": {},
        }

        response = client.put(
            f"/api/cron/{cronjob_id}", json=update_data, headers=authenticated_headers
        )
        assert response.status_code == 400
        assert "not registered" in response.json()["detail"]

    def test_update_cronjob_invalid_params(
        self, test_db, client, authenticated_headers
    ):
        create_data = {
            "identifier": "test_cronjob",
            "name": "Test Job",
            "cron": "0 0 * * *",
            "params": {"message": "Test", "delay_seconds": 5},
        }

        create_response = client.post(
            "/api/cron/", json=create_data, headers=authenticated_headers
        )
        cronjob_id = create_response.json()["cronjob_id"]

        update_data = {
            "identifier": "test_cronjob",
            "cron": "0 12 * * *",
            "params": {
                "message": "Valid message",
                "delay_seconds": "invalid_number",
            },
        }

        response = client.put(
            f"/api/cron/{cronjob_id}", json=update_data, headers=authenticated_headers
        )
        assert response.status_code == 400
        assert "Invalid parameters" in response.json()["detail"]

    def test_update_cronjob_scheduler_integration(
        self, test_db, client, authenticated_headers
    ):
        create_data = {
            "identifier": "test_cronjob",
            "name": "Scheduler Test Job",
            "cron": "0 0 * * *",
            "params": {"message": "Original", "delay_seconds": 0},
        }

        create_response = client.post(
            "/api/cron/", json=create_data, headers=authenticated_headers
        )
        cronjob_id = create_response.json()["cronjob_id"]

        update_data = {
            "identifier": "test_cronjob",
            "cron": "0 6 * * *",
            "params": {"message": "Updated", "delay_seconds": 0},
        }

        response = client.put(
            f"/api/cron/{cronjob_id}", json=update_data, headers=authenticated_headers
        )
        assert response.status_code == 200

        get_response = client.get(
            f"/api/cron/{cronjob_id}", headers=authenticated_headers
        )
        assert get_response.status_code == 200

        job = get_response.json()
        assert job["status"] == "active"
        assert job["cron"] == "0 6 * * *"
        assert job["params"]["message"] == "Updated"


class TestCronJobAPIAuthentication:
    def test_endpoints_require_authentication(self, client):
        endpoints = [
            ("GET", "/api/cron/registered"),
            ("POST", "/api/cron/"),
            ("GET", "/api/cron/some_cronjob_id"),
            ("POST", "/api/cron/some_cronjob_id/pause"),
            ("POST", "/api/cron/some_cronjob_id/resume"),
            ("DELETE", "/api/cron/some_cronjob_id"),
            ("GET", "/api/cron/some_cronjob_id/executions"),
        ]

        for method, endpoint in endpoints:
            if method == "GET":
                response = client.get(endpoint)
            elif method == "POST":
                response = client.post(endpoint, json={})
            elif method == "DELETE":
                response = client.delete(endpoint)
            else:
                continue

            assert response.status_code in [401, 403, 422], (
                f"{method} {endpoint} should require authentication"
            )
