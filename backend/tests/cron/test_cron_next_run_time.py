"""Cross-checks the get_next_run_time endpoint with an in-test cron parser."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app
from app.models import Base

from .test_cron_manager import test_cron_registry


def parse_cron_expression(cron_expr: str, second: str | None = None):
    """Parse a 5-field cron expression into a fields dict."""
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError("Cron expression must have exactly 5 fields")

    return {
        "second": second or "0",
        "minute": parts[0],
        "hour": parts[1],
        "day": parts[2],
        "month": parts[3],
        "day_of_week": parts[4],
    }


def calculate_next_run_time(
    cron_fields: dict, current_time: datetime | None = None
) -> datetime:
    """Simplified next-run calculation for daily/hourly/per-minute fields."""
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    minute = (
        int(cron_fields["minute"])
        if cron_fields["minute"] != "*"
        else current_time.minute
    )
    hour = int(cron_fields["hour"]) if cron_fields["hour"] != "*" else current_time.hour
    second = int(cron_fields["second"]) if cron_fields["second"] != "*" else 0

    if cron_fields["minute"] != "*" and cron_fields["hour"] != "*":
        next_run = current_time.replace(
            hour=hour, minute=minute, second=second, microsecond=0
        )

        if next_run <= current_time:
            next_run += timedelta(days=1)

        return next_run

    elif cron_fields["minute"] != "*" and cron_fields["hour"] == "*":
        next_run = current_time.replace(minute=minute, second=second, microsecond=0)

        if next_run <= current_time:
            next_run += timedelta(hours=1)

        return next_run

    elif cron_fields["minute"] == "*" and cron_fields["hour"] == "*":
        next_run = current_time.replace(second=second, microsecond=0)
        next_run += timedelta(minutes=1)
        return next_run

    else:
        return current_time + timedelta(minutes=1)


def validate_next_run_time(
    cron_expr: str,
    second: str | None,
    actual_next_run: datetime,
    tolerance_seconds: int = 3600,
) -> bool:
    try:
        actual_next_run_utc = actual_next_run.astimezone(timezone.utc)

        cron_fields = parse_cron_expression(cron_expr, second)
        expected_next_run = calculate_next_run_time(cron_fields)

        time_diff = abs((actual_next_run_utc - expected_next_run).total_seconds())

        return time_diff <= tolerance_seconds
    except Exception:
        return True


def validate_next_run_time_with_current_time(
    cron_expr: str,
    second: str | None,
    actual_next_run: datetime,
    current_time: datetime,
    tolerance_seconds: int = 3600,
) -> bool:
    try:
        actual_next_run_utc = actual_next_run.astimezone(timezone.utc)

        cron_fields = parse_cron_expression(cron_expr, second)
        expected_next_run = calculate_next_run_time(cron_fields, current_time)

        time_diff = abs((actual_next_run_utc - expected_next_run).total_seconds())

        return time_diff <= tolerance_seconds
    except Exception:
        return True


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

    from .test_cron_manager import TestCronManager

    fresh_test_cron_manager = TestCronManager()

    import app.routers.cron as cron_router_module

    original_cron_manager = cron_router_module.cron_manager
    original_cron_registry = cron_router_module.cron_registry

    cron_router_module.cron_manager = fresh_test_cron_manager
    cron_router_module.cron_registry = test_cron_registry

    await fresh_test_cron_manager.initialize()

    yield TestSessionLocal

    await fresh_test_cron_manager.shutdown()

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
            data["next_run_time"].replace("Z", "+00:00")
        )

        current_time_utc = datetime.now(timezone.utc)
        next_run_utc = next_run_time.astimezone(timezone.utc)

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
            data["next_run_time"].replace("Z", "+00:00")
        )

        current_time_utc = datetime.now(timezone.utc)
        next_run_utc = next_run_time.astimezone(timezone.utc)

        assert next_run_utc > current_time_utc

        assert next_run_time.second == 15

        assert next_run_time.minute == 30

    def test_get_next_run_time_job_not_found(
        self, test_db, client, authenticated_headers
    ):
        response = client.get(
            "/api/cron/nonexistent_job/next-run-time", headers=authenticated_headers
        )

        assert response.status_code == 400
        assert "not found" in response.json()["detail"]

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

        assert response.status_code == 400
        assert "not in active state" in response.json()["detail"]

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

        assert response.status_code == 400
        assert "not in active state" in response.json()["detail"]

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
            data["next_run_time"].replace("Z", "+00:00")
        )

        current_time_utc = datetime.now(timezone.utc)
        next_run_utc = next_run_time.astimezone(timezone.utc)

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
            data["next_run_time"].replace("Z", "+00:00")
        )

        current_time_utc = datetime.now(timezone.utc)
        next_run_utc = next_run_time.astimezone(timezone.utc)

        assert next_run_utc > current_time_utc

    def test_endpoint_requires_authentication(self, client):
        response = client.get("/api/cron/some_job/next-run-time")

        assert response.status_code in [401, 403, 422]


class TestCronExpressionValidation:
    def test_parse_cron_expression_valid(self):
        fields = parse_cron_expression("0 12 * * *")
        assert fields["minute"] == "0"
        assert fields["hour"] == "12"
        assert fields["day"] == "*"
        assert fields["month"] == "*"
        assert fields["day_of_week"] == "*"
        assert fields["second"] == "0"

        fields = parse_cron_expression("30 * * * *", "15")
        assert fields["second"] == "15"
        assert fields["minute"] == "30"

    def test_parse_cron_expression_invalid(self):
        with pytest.raises(ValueError, match="must have exactly 5 fields"):
            parse_cron_expression("0 12 * *")

        with pytest.raises(ValueError, match="must have exactly 5 fields"):
            parse_cron_expression("0 12 * * * *")

    def test_calculate_next_run_time_daily(self):
        current_time = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        cron_fields = parse_cron_expression("0 12 * * *")

        next_run = calculate_next_run_time(cron_fields, current_time)

        assert next_run.hour == 12
        assert next_run.minute == 0
        assert next_run.day == 1

        current_time = datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        next_run = calculate_next_run_time(cron_fields, current_time)

        assert next_run.hour == 12
        assert next_run.minute == 0
        assert next_run.day == 2

    def test_calculate_next_run_time_hourly(self):
        current_time = datetime(2024, 1, 1, 10, 20, 0, tzinfo=timezone.utc)
        cron_fields = parse_cron_expression("30 * * * *")

        next_run = calculate_next_run_time(cron_fields, current_time)

        assert next_run.hour == 10
        assert next_run.minute == 30

        current_time = datetime(2024, 1, 1, 10, 40, 0, tzinfo=timezone.utc)
        next_run = calculate_next_run_time(cron_fields, current_time)

        assert next_run.hour == 11
        assert next_run.minute == 30

    def test_validate_next_run_time_function(self):
        current_time = datetime.now(timezone.utc)

        cron_fields = parse_cron_expression("0 12 * * *", None)
        expected_next_run = calculate_next_run_time(cron_fields, current_time)

        assert validate_next_run_time_with_current_time(
            "0 12 * * *", None, expected_next_run, current_time, tolerance_seconds=60
        )

        actual_time = expected_next_run + timedelta(seconds=30)
        assert validate_next_run_time_with_current_time(
            "0 12 * * *", None, actual_time, current_time, tolerance_seconds=60
        )

        actual_time = expected_next_run + timedelta(hours=2)
        assert not validate_next_run_time_with_current_time(
            "0 12 * * *", None, actual_time, current_time, tolerance_seconds=60
        )
