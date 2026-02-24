"""Integration tests for template CRUD API endpoints."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import get_db
from app.main import api_app
from app.models import Base

YAML_TEMPLATE = """
version: '3.8'
services:
  mc:
    image: itzg/minecraft-server:latest
    container_name: mc-{name}
    ports:
      - "{game_port}:25565"
      - "{rcon_port}:25575"
    environment:
      EULA: "TRUE"
      VERSION: "{game_version}"
"""


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


class TestCreateTemplate:
    """Test template creation endpoint."""

    def test_create_template_success(self, test_client):
        """Test successful template creation."""
        response = test_client.post(
            "/api/templates/",
            json={
                "name": "test-template",
                "description": "Test template",
                "yaml_template": YAML_TEMPLATE,
                "variable_definitions": [
                    {"type": "string", "name": "name", "display_name": "Name"},
                    {"type": "int", "name": "game_port", "display_name": "Game Port"},
                    {"type": "int", "name": "rcon_port", "display_name": "RCON Port"},
                    {"type": "string", "name": "game_version", "display_name": "Version"},
                ],
            },
            headers=auth_headers(),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test-template"
        assert len(data["variable_definitions"]) == 4

    def test_create_template_validation_failure(self, test_client):
        """Test template creation fails with undefined variables (error)."""
        response = test_client.post(
            "/api/templates/",
            json={
                "name": "invalid-template",
                "yaml_template": YAML_TEMPLATE,
                "variable_definitions": [
                    {"type": "string", "name": "name", "display_name": "Name"},
                ],
            },
            headers=auth_headers(),
        )
        assert response.status_code == 400

    def test_create_template_with_unused_variables(self, test_client):
        """Test template creation succeeds with unused variables (warning only)."""
        response = test_client.post(
            "/api/templates/",
            json={
                "name": "unused-vars-template",
                "yaml_template": "name: {name}",
                "variable_definitions": [
                    {"type": "string", "name": "name", "display_name": "Name"},
                    {"type": "int", "name": "unused_port", "display_name": "Unused Port"},
                ],
            },
            headers=auth_headers(),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "unused-vars-template"
        assert len(data["variable_definitions"]) == 2

    def test_create_template_duplicate_name(self, test_client):
        """Test template creation fails with duplicate name."""
        payload = {
            "name": "duplicate-name",
            "yaml_template": "test: {var}",
            "variable_definitions": [{"type": "string", "name": "var", "display_name": "Var"}],
        }
        test_client.post("/api/templates/", json=payload, headers=auth_headers())
        response = test_client.post(
            "/api/templates/", json=payload, headers=auth_headers()
        )
        assert response.status_code == 409
        assert "已存在" in response.json()["detail"]

class TestGetTemplate:
    """Test template retrieval endpoints."""

    def test_list_templates(self, test_client):
        """Test listing all templates."""
        test_client.post(
            "/api/templates/",
            json={
                "name": "list-test",
                "yaml_template": "test: {var}",
                "variable_definitions": [{"type": "string", "name": "var", "display_name": "Var"}],
            },
            headers=auth_headers(),
        )
        response = test_client.get("/api/templates/", headers=auth_headers())
        assert response.status_code == 200
        assert len(response.json()) >= 1

    def test_get_template_details(self, test_client):
        """Test getting template details."""
        create_resp = test_client.post(
            "/api/templates/",
            json={
                "name": "detail-test",
                "yaml_template": "test: {var}",
                "variable_definitions": [{"type": "string", "name": "var", "display_name": "Var"}],
            },
            headers=auth_headers(),
        )
        template_id = create_resp.json()["id"]

        response = test_client.get(
            f"/api/templates/{template_id}", headers=auth_headers()
        )
        assert response.status_code == 200
        assert response.json()["name"] == "detail-test"

    def test_get_template_not_found(self, test_client):
        """Test getting non-existent template."""
        response = test_client.get("/api/templates/99999", headers=auth_headers())
        assert response.status_code == 404


class TestUpdateTemplate:
    """Test template update endpoint."""

    def test_update_template(self, test_client):
        """Test updating template fields."""
        create_resp = test_client.post(
            "/api/templates/",
            json={
                "name": "update-test",
                "yaml_template": "test: {var}",
                "variable_definitions": [{"type": "string", "name": "var", "display_name": "Var"}],
            },
            headers=auth_headers(),
        )
        template_id = create_resp.json()["id"]

        response = test_client.put(
            f"/api/templates/{template_id}",
            json={"description": "Updated description"},
            headers=auth_headers(),
        )
        assert response.status_code == 200
        assert response.json()["description"] == "Updated description"


class TestDeleteTemplate:
    """Test template deletion endpoint."""

    def test_delete_template(self, test_client):
        """Test deleting a template."""
        create_resp = test_client.post(
            "/api/templates/",
            json={
                "name": "delete-test",
                "yaml_template": "test: {var}",
                "variable_definitions": [{"type": "string", "name": "var", "display_name": "Var"}],
            },
            headers=auth_headers(),
        )
        template_id = create_resp.json()["id"]

        response = test_client.delete(
            f"/api/templates/{template_id}", headers=auth_headers()
        )
        assert response.status_code == 204


class TestTemplateSchema:
    """Test JSON Schema generation endpoint."""

    def test_get_json_schema(self, test_client):
        """Test getting JSON Schema for template."""
        create_resp = test_client.post(
            "/api/templates/",
            json={
                "name": "schema-test",
                "yaml_template": "port: {port}",
                "variable_definitions": [
                    {
                        "type": "int",
                        "name": "port",
                        "display_name": "Port",
                        "min_value": 1024,
                    }
                ],
            },
            headers=auth_headers(),
        )
        template_id = create_resp.json()["id"]

        response = test_client.get(
            f"/api/templates/{template_id}/schema", headers=auth_headers()
        )
        assert response.status_code == 200
        schema = response.json()["json_schema"]
        assert schema["properties"]["port"]["type"] == "integer"


class TestTemplatePreview:
    """Test YAML preview endpoint."""

    def test_preview_rendered_yaml(self, test_client):
        """Test previewing rendered YAML."""
        create_resp = test_client.post(
            "/api/templates/",
            json={
                "name": "preview-test",
                "yaml_template": "name: {name}\nport: {port}",
                "variable_definitions": [
                    {"type": "string", "name": "name", "display_name": "Name"},
                    {"type": "int", "name": "port", "display_name": "Port"},
                ],
            },
            headers=auth_headers(),
        )
        template_id = create_resp.json()["id"]

        response = test_client.post(
            f"/api/templates/{template_id}/preview",
            json={"variable_values": {"name": "test", "port": 25565}},
            headers=auth_headers(),
        )
        assert response.status_code == 200
        assert "name: test" in response.json()["rendered_yaml"]

    def test_preview_validation_failure(self, test_client):
        """Test preview fails with invalid values."""
        create_resp = test_client.post(
            "/api/templates/",
            json={
                "name": "preview-fail-test",
                "yaml_template": "port: {port}",
                "variable_definitions": [
                    {
                        "type": "int",
                        "name": "port",
                        "display_name": "Port",
                        "min_value": 1024,
                    }
                ],
            },
            headers=auth_headers(),
        )
        template_id = create_resp.json()["id"]

        response = test_client.post(
            f"/api/templates/{template_id}/preview",
            json={"variable_values": {"port": 80}},
            headers=auth_headers(),
        )
        assert response.status_code == 400
