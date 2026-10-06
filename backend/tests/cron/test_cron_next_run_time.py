import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.metadata import Base
from app.main import app
from app.runtime_resources import current_runtime
from tests.support.runtime import patch_settings, replace_runtime_resource

from .test_cron_manager import test_cron_registry


@pytest.fixture(scope="function")
async def test_db():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as temp_db:
        database_path = temp_db.name

    database_url = f"sqlite+aiosqlite:///{database_path}"
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

    original_db_session = db_module.get_session_factory()
    replace_runtime_resource(current_runtime(), "session_factory", TestSessionLocal)

    def get_test_session():
        return TestSessionLocal()

    original_get_session = manager_module.get_async_session
    manager_module.get_async_session = get_test_session

    from .test_cron_manager import TestCronManager

    fresh_test_cron_manager = TestCronManager()

    import app.routers.cron as cron_router_module

    original_cron_manager = cron_router_module.get_cron_manager()
    original_cron_registry = cron_router_module.get_cron_registry()

    replace_runtime_resource(current_runtime(), "cron_manager", fresh_test_cron_manager)
    replace_runtime_resource(current_runtime(), "cron_registry", test_cron_registry)

    await fresh_test_cron_manager.initialize()

    yield TestSessionLocal

    await fresh_test_cron_manager.shutdown()

    replace_runtime_resource(current_runtime(), "session_factory", original_db_session)
    manager_module.get_async_session = original_get_session
    replace_runtime_resource(current_runtime(), "cron_manager", original_cron_manager)
    replace_runtime_resource(current_runtime(), "cron_registry", original_cron_registry)

    await engine.dispose()
    Path(database_path).unlink(missing_ok=True)


@pytest.fixture
def client():
    with patch_settings() as mock_settings:
        mock_settings.master_token = "test_master_token"
        client = TestClient(app)
        yield client


@pytest.fixture
async def authenticated_headers():
    return {"Authorization": "Bearer test_master_token"}


class TestCronJobNextRunTime:
    def test_get_next_run_time_for_active_job(
        self, test_db, client, authenticated_headers
    ):
        cronjob_data = {
            "identifier": "test_cronjob",
            "name": "Daily Noon Job",
            "cron": "0 12 * * *",
            "params": {"message": "Daily job", "delay_seconds": 0},
        }

        create_response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )
        assert create_response.status_code == 200
        cronjob_id = create_response.json()["cronjob_id"]

        response = client.get(
            f"/api/cron/{cronjob_id}/next-run-time", headers=authenticated_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["cronjob_id"] == cronjob_id
        assert "next_run_time" in data

        next_run_time = datetime.fromisoformat(
            data["next_run_time"]
        )

        current_time_utc = datetime.now(UTC)
        next_run_utc = next_run_time.astimezone(UTC)

        assert next_run_utc > current_time_utc

        assert next_run_utc.minute == 0

    def test_get_next_run_time_with_second_field(
        self, test_db, client, authenticated_headers
    ):
        cronjob_data = {
            "identifier": "test_cronjob",
            "name": "Hourly Job with Seconds",
            "cron": "30 * * * *",
            "second": "15",
            "params": {"message": "Hourly with seconds", "delay_seconds": 0},
        }

        create_response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )
        assert create_response.status_code == 200
        cronjob_id = create_response.json()["cronjob_id"]

        response = client.get(
            f"/api/cron/{cronjob_id}/next-run-time", headers=authenticated_headers
        )

        assert response.status_code == 200
        data = response.json()

        next_run_time = datetime.fromisoformat(
            data["next_run_time"]
        )

        current_time_utc = datetime.now(UTC)
        next_run_utc = next_run_time.astimezone(UTC)

        assert next_run_utc > current_time_utc

        assert next_run_time.second == 15

        assert next_run_time.minute == 30

    def test_get_next_run_time_job_not_found(
        self, test_db, client, authenticated_headers
    ):
        response = client.get(
            "/api/cron/nonexistent_job/next-run-time", headers=authenticated_headers
        )

        assert response.status_code == 404
        assert "不存在" in response.json()["detail"]

    def test_get_next_run_time_paused_job(self, test_db, client, authenticated_headers):
        cronjob_data = {
            "identifier": "test_cronjob",
            "name": "Paused Job",
            "cron": "0 * * * *",
            "params": {"message": "Paused job", "delay_seconds": 0},
        }

        create_response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )
        assert create_response.status_code == 200
        cronjob_id = create_response.json()["cronjob_id"]

        pause_response = client.post(
            f"/api/cron/{cronjob_id}/pause", headers=authenticated_headers
        )
        assert pause_response.status_code == 200

        response = client.get(
            f"/api/cron/{cronjob_id}/next-run-time", headers=authenticated_headers
        )

        assert response.status_code == 409
        assert "未处于运行中" in response.json()["detail"]

    def test_get_next_run_time_cancelled_job(
        self, test_db, client, authenticated_headers
    ):
        cronjob_data = {
            "identifier": "test_cronjob",
            "name": "Cancelled Job",
            "cron": "0 * * * *",
            "params": {"message": "Cancelled job", "delay_seconds": 0},
        }

        create_response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )
        assert create_response.status_code == 200
        cronjob_id = create_response.json()["cronjob_id"]

        cancel_response = client.delete(
            f"/api/cron/{cronjob_id}", headers=authenticated_headers
        )
        assert cancel_response.status_code == 200

        response = client.get(
            f"/api/cron/{cronjob_id}/next-run-time", headers=authenticated_headers
        )

        assert response.status_code == 409
        assert "未处于运行中" in response.json()["detail"]

    def test_multiple_cron_expressions(self, test_db, client, authenticated_headers):
        cronjob_data = {
            "identifier": "test_cronjob",
            "name": "Daily at 6 PM",
            "cron": "0 18 * * *",
            "params": {"message": "Should run daily at 6 PM", "delay_seconds": 0},
        }

        create_response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )
        assert create_response.status_code == 200
        cronjob_id = create_response.json()["cronjob_id"]

        response = client.get(
            f"/api/cron/{cronjob_id}/next-run-time", headers=authenticated_headers
        )

        assert response.status_code == 200
        data = response.json()

        next_run_time = datetime.fromisoformat(
            data["next_run_time"]
        )

        current_time_utc = datetime.now(UTC)
        next_run_utc = next_run_time.astimezone(UTC)

        assert next_run_utc > current_time_utc

        client.delete(f"/api/cron/{cronjob_id}", headers=authenticated_headers)

    def test_resumed_job_has_next_run_time(
        self, test_db, client, authenticated_headers
    ):
        cronjob_data = {
            "identifier": "test_cronjob",
            "name": "Resume Test Job",
            "cron": "0 18 * * *",
            "params": {"message": "Resume test", "delay_seconds": 0},
        }

        create_response = client.post(
            "/api/cron/", json=cronjob_data, headers=authenticated_headers
        )
        assert create_response.status_code == 200
        cronjob_id = create_response.json()["cronjob_id"]

        client.post(f"/api/cron/{cronjob_id}/pause", headers=authenticated_headers)

        resume_response = client.post(
            f"/api/cron/{cronjob_id}/resume", headers=authenticated_headers
        )
        assert resume_response.status_code == 200

        response = client.get(
            f"/api/cron/{cronjob_id}/next-run-time", headers=authenticated_headers
        )

        assert response.status_code == 200
        data = response.json()

        next_run_time = datetime.fromisoformat(
            data["next_run_time"]
        )

        current_time_utc = datetime.now(UTC)
        next_run_utc = next_run_time.astimezone(UTC)

        assert next_run_utc > current_time_utc

    def test_endpoint_requires_authentication(self, client):
        response = client.get("/api/cron/some_job/next-run-time")

        assert response.status_code in [401, 403, 422]
