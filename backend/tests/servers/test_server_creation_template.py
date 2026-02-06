"""Integration tests for template-mode server creation."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import get_db
from app.main import api_app
from app.minecraft import DockerMCManager
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
      MEMORY: "2G"
    volumes:
      - ./data:/data
    restart: unless-stopped
"""


@pytest.fixture
def temp_server_path():
    """Create a temporary directory for server files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


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
def test_client(temp_server_path, test_db):
    """Create TestClient with mocked dependencies."""

    async def override_get_db():
        async with test_db() as session:
            yield session

    api_app.dependency_overrides[get_db] = override_get_db

    with patch("app.config.settings.server_path", temp_server_path):
        with patch("app.config.settings.master_token", "test-master-token"):
            real_mc_manager = DockerMCManager(temp_server_path)
            with patch("app.routers.servers.create.docker_mc_manager", real_mc_manager):
                with patch(
                    "app.servers.port_utils.docker_mc_manager", real_mc_manager
                ):
                    with patch(
                        "app.servers.port_utils.get_system_used_ports",
                        return_value=set(),
                    ):
                        with patch(
                            "app.routers.servers.create.player_system_manager.start_server_monitoring",
                            new_callable=AsyncMock,
                        ):
                            client = TestClient(api_app, raise_server_exceptions=False)
                            yield client

    api_app.dependency_overrides.pop(get_db, None)


def auth_headers():
    return {"Authorization": "Bearer test-master-token"}


def create_template(client) -> int:
    """Helper to create a template and return its ID."""
    response = client.post(
        "/api/templates/",
        json={
            "name": "test-template",
            "yaml_template": YAML_TEMPLATE,
            "variable_definitions": [
                {
                    "type": "string",
                    "name": "name",
                    "display_name": "Name",
                    "pattern": "^[a-z0-9-]+$",
                },
                {
                    "type": "int",
                    "name": "game_port",
                    "display_name": "Game Port",
                    "min_value": 1024,
                },
                {"type": "int", "name": "rcon_port", "display_name": "RCON Port"},
                {"type": "string", "name": "game_version", "display_name": "Version"},
            ],
        },
        headers=auth_headers(),
    )
    return response.json()["id"]


class TestTemplateServerCreation:
    """Test server creation using templates."""

    def test_template_mode_success(self, test_client):
        """Test successful server creation with template."""
        template_id = create_template(test_client)

        response = test_client.post(
            "/api/servers/template-server",
            json={
                "template_id": template_id,
                "variable_values": {
                    "name": "template-server",
                    "game_port": 25565,
                    "rcon_port": 25575,
                    "game_version": "1.20.1",
                },
            },
            headers=auth_headers(),
        )
        assert response.status_code == 200
        assert response.json()["game_port"] == 25565

    def test_template_not_found(self, test_client):
        """Test creation fails with non-existent template."""
        response = test_client.post(
            "/api/servers/test-server",
            json={
                "template_id": 99999,
                "variable_values": {"name": "test"},
            },
            headers=auth_headers(),
        )
        assert response.status_code == 404

    def test_variable_values_validation_failure(self, test_client):
        """Test creation fails with invalid variable values."""
        template_id = create_template(test_client)

        response = test_client.post(
            "/api/servers/invalid-server",
            json={
                "template_id": template_id,
                "variable_values": {
                    "name": "INVALID_NAME",  # Doesn't match pattern
                    "game_port": 25565,
                    "rcon_port": 25575,
                    "game_version": "1.20.1",
                },
            },
            headers=auth_headers(),
        )
        assert response.status_code == 400

    def test_missing_variable_values(self, test_client):
        """Test creation fails without variable_values in template mode."""
        template_id = create_template(test_client)

        response = test_client.post(
            "/api/servers/test-server",
            json={"template_id": template_id},
            headers=auth_headers(),
        )
        assert response.status_code == 400
        assert "variable_values" in response.json()["detail"]

    def test_mutual_exclusion(self, test_client):
        """Test creation fails with both yaml_content and template_id."""
        response = test_client.post(
            "/api/servers/test-server",
            json={
                "yaml_content": "test: yaml",
                "template_id": 1,
                "variable_values": {},
            },
            headers=auth_headers(),
        )
        assert response.status_code == 400
