"""Integration tests for default variables API endpoints."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import get_db
from app.main import api_app
from app.models import Base


@pytest.fixture
async def test_db():
    """Create a test database."""
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()
    database_url = f"sqlite+aiosqlite:///{temp_db.name}"
    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestSessionLocal = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    yield TestSessionLocal

    await engine.dispose()
    Path(temp_db.name).unlink(missing_ok=True)


@pytest.fixture
def test_client(test_db):
    """Create TestClient with test database."""
    from unittest.mock import patch

    async def override_get_db():
        async with test_db() as session:
            yield session

    api_app.dependency_overrides[get_db] = override_get_db

    with patch("app.config.settings.master_token", "test-master-token"):
        client = TestClient(api_app, raise_server_exceptions=False)
        yield client

    api_app.dependency_overrides.pop(get_db, None)


def auth_headers():
    return {"Authorization": "Bearer test-master-token"}


class TestGetDefaultVariables:
    """Test getting default variables."""

    def test_get_default_variables(self, test_client):
        """Test getting default variables returns list."""
        response = test_client.get(
            "/api/templates/default-variables", headers=auth_headers()
        )
        assert response.status_code == 200
        data = response.json()
        assert "variable_definitions" in data
        assert isinstance(data["variable_definitions"], list)


class TestUpdateDefaultVariables:
    """Test updating default variables."""

    def test_update_default_variables(self, test_client):
        """Test updating default variables."""
        response = test_client.put(
            "/api/templates/default-variables",
            json={
                "variable_definitions": [
                    {"type": "string", "name": "custom_var", "display_name": "Custom"},
                    {"type": "int", "name": "port", "display_name": "Port"},
                ]
            },
            headers=auth_headers(),
        )
        assert response.status_code == 200
        assert len(response.json()["variable_definitions"]) == 2

    def test_update_duplicate_names_rejected(self, test_client):
        """Test updating with duplicate names fails."""
        response = test_client.put(
            "/api/templates/default-variables",
            json={
                "variable_definitions": [
                    {"type": "string", "name": "dup", "display_name": "Dup 1"},
                    {"type": "int", "name": "dup", "display_name": "Dup 2"},
                ]
            },
            headers=auth_headers(),
        )
        assert response.status_code == 400
        assert "重复" in response.json()["detail"]
