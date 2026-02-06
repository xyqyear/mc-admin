"""Integration tests for template configuration endpoints."""

import json
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

def get_traditional_yaml(server_id: str, game_port: int = 25566, rcon_port: int = 25576):
    """Generate traditional YAML for a specific server."""
    return f"""
version: '3.8'
services:
  mc:
    image: itzg/minecraft-server:latest
    container_name: mc-{server_id}
    ports:
      - "{game_port}:25565"
      - "{rcon_port}:25575"
    environment:
      EULA: "TRUE"
      VERSION: "1.20.1"
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
                    "app.routers.servers.template_config.docker_mc_manager",
                    real_mc_manager,
                ):
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
                                client = TestClient(
                                    api_app, raise_server_exceptions=False
                                )
                                yield client

    api_app.dependency_overrides.pop(get_db, None)


def auth_headers():
    return {"Authorization": "Bearer test-master-token"}


def create_template(client) -> int:
    """Helper to create a template and return its ID."""
    response = client.post(
        "/api/templates/",
        json={
            "name": "config-test-template",
            "yaml_template": YAML_TEMPLATE,
            "variables": [
                {"type": "string", "name": "name", "display_name": "Name"},
                {"type": "int", "name": "game_port", "display_name": "Game Port"},
                {"type": "int", "name": "rcon_port", "display_name": "RCON Port"},
                {"type": "string", "name": "game_version", "display_name": "Version"},
            ],
        },
        headers=auth_headers(),
    )
    return response.json()["id"]


def create_template_server(client, template_id: int, server_id: str):
    """Helper to create a server using template."""
    return client.post(
        f"/api/servers/{server_id}",
        json={
            "template_id": template_id,
            "variable_values": {
                "name": server_id,
                "game_port": 25565,
                "rcon_port": 25575,
                "game_version": "1.20.1",
            },
        },
        headers=auth_headers(),
    )


class TestGetTemplateConfig:
    """Test getting template configuration."""

    def test_get_template_config(self, test_client):
        """Test getting template config for template-created server."""
        template_id = create_template(test_client)
        create_template_server(test_client, template_id, "config-server")

        response = test_client.get(
            "/api/servers/config-server/template-config", headers=auth_headers()
        )
        assert response.status_code == 200
        data = response.json()
        assert data["server_id"] == "config-server"
        assert data["template_id"] == template_id
        assert "json_schema" in data
        assert data["variable_values"]["game_port"] == 25565

    def test_get_config_non_template_server(self, test_client):
        """Test getting config fails for non-template server."""
        # Create traditional server
        test_client.post(
            "/api/servers/traditional-server",
            json={"yaml_content": get_traditional_yaml("traditional-server")},
            headers=auth_headers(),
        )

        response = test_client.get(
            "/api/servers/traditional-server/template-config", headers=auth_headers()
        )
        assert response.status_code == 400
        assert "不是使用模板创建" in response.json()["detail"]


class TestTemplateConfigPreview:
    """Test template config preview endpoint."""

    def test_preview_template_based(self, test_client):
        """Test preview returns is_template_based=True for template server."""
        template_id = create_template(test_client)
        create_template_server(test_client, template_id, "preview-server")

        response = test_client.get(
            "/api/servers/preview-server/template-config/preview",
            headers=auth_headers(),
        )
        assert response.status_code == 200
        assert response.json()["is_template_based"] is True

    def test_preview_non_template(self, test_client):
        """Test preview returns is_template_based=False for traditional server."""
        test_client.post(
            "/api/servers/trad-preview",
            json={"yaml_content": get_traditional_yaml("trad-preview", 25567, 25577)},
            headers=auth_headers(),
        )

        response = test_client.get(
            "/api/servers/trad-preview/template-config/preview",
            headers=auth_headers(),
        )
        assert response.status_code == 200
        assert response.json()["is_template_based"] is False
