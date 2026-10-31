"""Integration tests for default variables API endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_api_app
from app.runtime_resources import current_runtime


@pytest.fixture
async def test_db(db_session_factory):
    return db_session_factory


@pytest.fixture
def test_client(test_db):
    """Create TestClient with test database."""
    from unittest.mock import patch

    with (
        patch.object(current_runtime().settings, "master_token", "test-master-token"),
        TestClient(create_api_app(current_runtime()), raise_server_exceptions=False) as client,
    ):
        yield client



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
        saved = response.json()["variable_definitions"]
        assert [(row["name"], row["type"]) for row in saved] == [("custom_var", "string"), ("port", "int")]
        reloaded = test_client.get("/api/templates/default-variables", headers=auth_headers())
        assert reloaded.status_code == 200
        assert reloaded.json()["variable_definitions"] == saved

    def test_update_duplicate_names_rejected(self, test_client):
        """Test updating with duplicate names fails."""
        before = test_client.get("/api/templates/default-variables", headers=auth_headers()).json()
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
        assert test_client.get("/api/templates/default-variables", headers=auth_headers()).json() == before
