from tests.support.tasks import task_result

"""Integration tests for template-mode server creation."""
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_api_app
from app.minecraft import DockerMCManager
from app.operations.journal import OperationJournal
from app.operations.journal_types import OperationState
from app.runtime_resources import current_runtime
from app.servers.models import Server
from tests.support.runtime import patch_runtime_resource

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
      SERVER_PORT: "25565"
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
async def test_db(db_session_factory):
    return db_session_factory


@pytest.fixture
def test_client(temp_server_path, test_db):
    """Create TestClient with mocked dependencies."""
    current_runtime().journal = OperationJournal(test_db)

    with (
        patch.object(current_runtime().settings, 'server_path', temp_server_path),
        patch.object(current_runtime().settings, 'master_token', 'test-master-token'),
    ):
        real_mc_manager = DockerMCManager(temp_server_path)
        with (
            patch_runtime_resource('docker_mc_manager', real_mc_manager),
            patch('app.servers.port_utils.get_system_used_ports', return_value=set()),
            patch.object(current_runtime().log_monitor, 'start_server', new_callable=AsyncMock),
            patch.object(current_runtime().dns_manager, 'update', new_callable=AsyncMock),
            TestClient(create_api_app(current_runtime()), raise_server_exceptions=False) as client,
        ):
            yield client



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
        assert task_result(test_client, response)["game_port"] == 25565

        async def persisted_creation():
            runtime = current_runtime()
            record = await OperationJournal(runtime.database.session_factory).get(response.json()["task_id"])
            assert record is not None and record.state is OperationState.SUCCEEDED
            assert record.writers_stopped and record.actor_id == 0
            async with runtime.database.session_factory() as session:
                server = (await session.scalars(select(Server).where(Server.server_id == "template-server"))).one()
                assert server.template_id == template_id
                assert server.variable_values_json is not None
                assert server.template_snapshot_json is not None
                values = json.loads(server.variable_values_json)
                assert values == {"name": "template-server", "game_port": 25565, "rcon_port": 25575, "game_version": "1.20.1"}
                assert json.loads(server.template_snapshot_json)["template_id"] == template_id
            compose = runtime.settings.server_path / "template-server" / "docker-compose.yml"
            assert compose.read_text() == YAML_TEMPLATE.format(**values)

        assert test_client.portal is not None
        test_client.portal.call(persisted_creation)

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

    def test_empty_variable_values_with_static_template(self, test_client):
        """Test creation succeeds with empty variable_values for a no-variable template."""
        static_yaml = """
version: '3.8'
services:
  mc:
    image: itzg/minecraft-server:latest
    container_name: mc-static-server
    ports:
      - "25570:25565"
      - "25580:25575"
    environment:
      SERVER_PORT: "25565"
      EULA: "TRUE"
      VERSION: "1.20.1"
    volumes:
      - ./data:/data
    restart: unless-stopped
"""
        response = test_client.post(
            "/api/templates/",
            json={
                "name": "static-template",
                "yaml_template": static_yaml,
                "variable_definitions": [],
            },
            headers=auth_headers(),
        )
        static_template_id = response.json()["id"]

        response = test_client.post(
            "/api/servers/static-server",
            json={
                "template_id": static_template_id,
                "variable_values": {},
            },
            headers=auth_headers(),
        )
        task_result(test_client, response)

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
