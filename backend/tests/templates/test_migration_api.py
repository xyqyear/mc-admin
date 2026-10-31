"""Integration tests for template migration API endpoints."""
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_api_app
from app.operations.journal import OperationJournal
from app.operations.journal_types import OperationState
from app.runtime_resources import current_runtime
from app.servers.models import Server, ServerStatus
from app.templates import (
    IntVariableDefinition,
    StringVariableDefinition,
)
from app.templates.models import serialize_variable_definitions
from app.templates.tables import ServerTemplate

YAML_TEMPLATE = """\
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

VARIABLE_DEFS = [
    StringVariableDefinition(name="name", display_name="Server Name"),
    IntVariableDefinition(
        name="game_port", display_name="Game Port", min_value=1024, max_value=65535
    ),
    IntVariableDefinition(
        name="rcon_port", display_name="RCON Port", min_value=1024, max_value=65535
    ),
    StringVariableDefinition(name="game_version", display_name="Game Version"),
]

VARIABLE_VALUES = {
    "name": "survival",
    "game_port": 30000,
    "rcon_port": 30001,
    "game_version": "1.20.4",
}

# Rendered version of YAML_TEMPLATE with VARIABLE_VALUES
RENDERED_YAML = """\
version: '3.8'
services:
  mc:
    image: itzg/minecraft-server:latest
    container_name: mc-survival
    ports:
      - "30000:25565"
      - "30001:25575"
    environment:
      EULA: "TRUE"
      VERSION: "1.20.4"
"""


@pytest.fixture
async def test_db(db_session_factory):
    return db_session_factory


@pytest.fixture
def mock_docker_instance(isolated_runtime, monkeypatch):
    from app.minecraft import MCServerStatus

    manager = isolated_runtime.docker_mc_manager
    instance = manager.get_instance("test-server")
    compose = instance.get_project_path() / "docker-compose.yml"
    compose.parent.mkdir()
    compose.write_text(RENDERED_YAML)
    monkeypatch.setattr(instance, "set_compose", compose.write_text, raising=False)
    monkeypatch.setattr(instance, "exists", AsyncMock(wraps=instance.exists))
    monkeypatch.setattr(instance, "get_status", AsyncMock(return_value=MCServerStatus.EXISTS))
    monkeypatch.setattr(instance, "created", AsyncMock(return_value=False))
    monkeypatch.setattr(instance, "down", AsyncMock())
    monkeypatch.setattr(instance, "up", AsyncMock())
    monkeypatch.setattr(manager, "get_instance", lambda _: instance)
    monkeypatch.setattr("app.servers.port_utils.get_system_used_ports", lambda: set())
    return instance


@pytest.fixture
def test_client(test_db, mock_docker_instance, isolated_runtime):
    isolated_runtime.journal = OperationJournal(test_db)
    with (
        patch.object(isolated_runtime.settings, "master_token", "test-master-token"),
        TestClient(create_api_app(current_runtime()), raise_server_exceptions=False) as client,
    ):
        yield client



def auth_headers():
    return {"Authorization": "Bearer test-master-token"}


def assert_completed_conversion(client, response, database, template_id, values):
    import asyncio

    assert response.status_code == 200, response.text
    assert response.json()["skipped_rebuild"] is False
    task_id = response.json()["task_id"]
    assert task_id

    async def observe():
        future = current_runtime().task_manager.get_future(task_id)
        assert future is not None
        result = await asyncio.wait_for(future, timeout=5)
        assert result.success, result.error
        record = await OperationJournal(database).get(task_id)
        assert record is not None and record.state is OperationState.SUCCEEDED
        assert record.writers_stopped and record.actor_id == 0
        async with database() as session:
            server = (await session.scalars(select(Server).where(Server.server_id == "test-server"))).one()
            assert server.template_id == template_id
            assert json.loads(server.variable_values_json) == values
            snapshot = json.loads(server.template_snapshot_json)
            assert snapshot["template_id"] == template_id
        return result

    assert client.portal is not None
    result = client.portal.call(observe)
    detail = client.get(f"/api/tasks/{task_id}", headers=auth_headers())
    assert detail.status_code == 200 and detail.json()["status"] == "completed"
    compose = current_runtime().settings.server_path / "test-server" / "docker-compose.yml"
    assert compose.read_text() == YAML_TEMPLATE.format(**values)
    assert result.data["game_port"] == values["game_port"]
    assert not list(compose.parent.glob(".mc-admin-configuration-*.tmp"))


async def create_test_server(
    db_factory,
    server_id: str = "test-server",
    template_id: int | None = None,
    snapshot_json: str | None = None,
    values_json: str | None = None,
):
    """Helper to create a test server in the database."""
    async with db_factory() as session:
        server = Server(
            server_id=server_id,
            status=ServerStatus.ACTIVE,
            template_id=template_id,
            template_snapshot_json=snapshot_json,
            variable_values_json=values_json,
        )
        session.add(server)
        await session.commit()
        return server


async def create_test_template(
    db_factory,
    name: str = "test-template",
    yaml_template: str = YAML_TEMPLATE,
    variable_definitions=None,
):
    """Helper to create a test template in the database."""
    if variable_definitions is None:
        variable_definitions = VARIABLE_DEFS
    async with db_factory() as session:
        template = ServerTemplate(
            name=name,
            yaml_template=yaml_template,
            variable_definitions_json=serialize_variable_definitions(
                variable_definitions
            ),
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)
        return template


# ============================================================
# Convert to Direct Mode
# ============================================================


class TestConvertToDirectMode:
    """Tests for POST /servers/{id}/convert-to-direct endpoint."""

    @pytest.fixture(autouse=True)
    async def setup(self, test_db):
        self.db = test_db

    async def _setup_template_server(self):
        template = await create_test_template(self.db)
        await create_test_server(
            self.db,
            template_id=template.id,
            snapshot_json='{"template_id": 1}',
            values_json=json.dumps(VARIABLE_VALUES),
        )
        return template

    def test_convert_to_direct_success(self, test_client, isolated_runtime):
        """Convert a template-based server to direct mode."""
        import asyncio

        asyncio.get_event_loop().run_until_complete(self._setup_template_server())

        response = test_client.post(
            "/api/servers/test-server/convert-to-direct",
            headers=auth_headers(),
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

        async def persisted_fields():
            async with self.db() as session:
                result = await session.execute(select(
                    Server.template_id,
                    Server.template_snapshot_json,
                    Server.variable_values_json,
                ).where(Server.server_id == "test-server"))
                return tuple(result.one())

        assert asyncio.get_event_loop().run_until_complete(persisted_fields()) == (None, None, None)
        compose = isolated_runtime.settings.server_path / "test-server" / "docker-compose.yml"
        assert compose.read_bytes() == RENDERED_YAML.encode()

    def test_convert_already_direct_mode(self, test_client):
        """Converting a server already in direct mode returns 400."""
        import asyncio

        asyncio.get_event_loop().run_until_complete(
            create_test_server(self.db, template_id=None)
        )

        response = test_client.post(
            "/api/servers/test-server/convert-to-direct",
            headers=auth_headers(),
        )
        assert response.status_code == 400
        assert "已经是直接编辑模式" in response.json()["detail"]

    def test_convert_server_not_found(self, test_client):
        """Converting a non-existent server returns 404."""
        response = test_client.post(
            "/api/servers/nonexistent/convert-to-direct",
            headers=auth_headers(),
        )
        assert response.status_code == 404

# ============================================================
# Extract Variables
# ============================================================


class TestExtractVariables:
    """Tests for POST /servers/{id}/extract-variables endpoint."""

    @pytest.fixture(autouse=True)
    async def setup(self, test_db):
        self.db = test_db

    def test_extract_variables_success(self, test_client, mock_docker_instance):
        """Extract variables from compose file successfully."""
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(self.db)
        )
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))
        mock_docker_instance.set_compose(RENDERED_YAML)

        response = test_client.post(
            "/api/servers/test-server/extract-variables",
            json={"template_id": template.id},
            headers=auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["extracted_values"]["name"] == "survival"
        assert data["extracted_values"]["game_port"] == 30000
        assert data["extracted_values"]["rcon_port"] == 30001
        assert data["extracted_values"]["game_version"] == "1.20.4"
        assert isinstance(data["json_schema"], dict)
        assert isinstance(data["variable_definitions"], list)
        assert len(data["variable_definitions"]) == 4

    def test_extract_variables_with_warnings(self, test_client, mock_docker_instance):
        """Extract variables when some are missing produces warnings."""
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(self.db)
        )
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))
        # Return compose that doesn't match template well
        mock_docker_instance.set_compose("version: '3.8'\nservices:\n  mc:\n    image: test")

        response = test_client.post(
            "/api/servers/test-server/extract-variables",
            json={"template_id": template.id},
            headers=auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["warnings"]) > 0

    def test_extract_template_not_found(self, test_client):
        """Extract variables with non-existent template returns 404."""
        import asyncio

        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))

        response = test_client.post(
            "/api/servers/test-server/extract-variables",
            json={"template_id": 99999},
            headers=auth_headers(),
        )
        assert response.status_code == 404
        assert "模板不存在" in response.json()["detail"]

    def test_extract_server_not_found(self, test_client):
        """Extract variables for non-existent server returns 404."""
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(self.db)
        )

        response = test_client.post(
            "/api/servers/nonexistent/extract-variables",
            json={"template_id": template.id},
            headers=auth_headers(),
        )
        assert response.status_code == 404

    def test_extract_server_directory_missing(
        self, test_client, mock_docker_instance
    ):
        """Extract variables when server directory doesn't exist returns 404."""
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(self.db)
        )
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))
        mock_docker_instance.exists.return_value = False

        response = test_client.post(
            "/api/servers/test-server/extract-variables",
            json={"template_id": template.id},
            headers=auth_headers(),
        )
        assert response.status_code == 404
        assert "服务器目录不存在" in response.json()["detail"]

    def test_extract_multiple_variables_per_line(
        self, test_client, mock_docker_instance
    ):
        """Extract multiple variables from a single port mapping line."""
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(self.db)
        )
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))
        mock_docker_instance.set_compose(RENDERED_YAML)

        response = test_client.post(
            "/api/servers/test-server/extract-variables",
            json={"template_id": template.id},
            headers=auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        # Both port variables are on the same line format "{game_port}:25565"
        assert data["extracted_values"]["game_port"] == 30000
        assert data["extracted_values"]["rcon_port"] == 30001


# ============================================================
# Check Conversion
# ============================================================


class TestCheckConversion:
    """Tests for POST /servers/{id}/check-conversion endpoint."""

    @pytest.fixture(autouse=True)
    async def setup(self, test_db):
        self.db = test_db

    def test_no_rebuild_needed(self, test_client, mock_docker_instance):
        """Semantically equal YAML requires no rebuild."""
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(self.db)
        )
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))
        mock_docker_instance.set_compose(RENDERED_YAML)

        response = test_client.post(
            "/api/servers/test-server/check-conversion",
            json={
                "template_id": template.id,
                "variable_values": VARIABLE_VALUES,
            },
            headers=auth_headers(),
        )
        assert response.status_code == 200
        assert response.json()["requires_rebuild"] is False

    def test_requires_rebuild(self, test_client, mock_docker_instance):
        """Different YAML requires rebuild."""
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(self.db)
        )
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))
        # Current compose is different from what template would render
        mock_docker_instance.set_compose("version: '3.8'\nservices:\n  mc:\n    image: different")

        response = test_client.post(
            "/api/servers/test-server/check-conversion",
            json={
                "template_id": template.id,
                "variable_values": VARIABLE_VALUES,
            },
            headers=auth_headers(),
        )
        assert response.status_code == 200
        assert response.json()["requires_rebuild"] is True

    def test_dict_order_difference_no_rebuild(
        self, test_client, mock_docker_instance
    ):
        """Dict key order difference doesn't require rebuild."""
        import asyncio

        # Simple template with single variable
        simple_template = "name: {name}\nport: 25565"
        simple_vars = [
            StringVariableDefinition(name="name", display_name="Name")
        ]
        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(
                self.db,
                yaml_template=simple_template,
                variable_definitions=simple_vars,
            )
        )
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))
        # Reordered keys but same content
        mock_docker_instance.set_compose("port: 25565\nname: survival")

        response = test_client.post(
            "/api/servers/test-server/check-conversion",
            json={
                "template_id": template.id,
                "variable_values": {"name": "survival"},
            },
            headers=auth_headers(),
        )
        assert response.status_code == 200
        assert response.json()["requires_rebuild"] is False

    def test_list_order_difference_requires_rebuild(
        self, test_client, mock_docker_instance
    ):
        """List order difference requires rebuild."""
        import asyncio

        list_template = "ports:\n  - {port_a}\n  - {port_b}"
        list_vars = [
            IntVariableDefinition(name="port_a", display_name="Port A"),
            IntVariableDefinition(name="port_b", display_name="Port B"),
        ]
        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(
                self.db,
                yaml_template=list_template,
                variable_definitions=list_vars,
            )
        )
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))
        # Reversed list order
        mock_docker_instance.set_compose("ports:\n  - 8081\n  - 8080")

        response = test_client.post(
            "/api/servers/test-server/check-conversion",
            json={
                "template_id": template.id,
                "variable_values": {"port_a": 8080, "port_b": 8081},
            },
            headers=auth_headers(),
        )
        assert response.status_code == 200
        assert response.json()["requires_rebuild"] is True

    def test_validation_error(self, test_client):
        """Invalid variable values return 400."""
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(self.db)
        )
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))

        response = test_client.post(
            "/api/servers/test-server/check-conversion",
            json={
                "template_id": template.id,
                "variable_values": {},  # Missing required values
            },
            headers=auth_headers(),
        )
        assert response.status_code == 400

    def test_server_not_found(self, test_client):
        """Non-existent server returns 404."""
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(self.db)
        )

        response = test_client.post(
            "/api/servers/nonexistent/check-conversion",
            json={
                "template_id": template.id,
                "variable_values": VARIABLE_VALUES,
            },
            headers=auth_headers(),
        )
        assert response.status_code == 404


# ============================================================
# Convert to Template Mode
# ============================================================


class TestConvertToTemplateMode:
    """Tests for POST /servers/{id}/convert-to-template endpoint."""

    @pytest.fixture(autouse=True)
    async def setup(self, test_db):
        self.db = test_db

    def test_convert_no_rebuild(self, test_client, mock_docker_instance):
        """Convert when YAML is semantically equal skips rebuild."""
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(self.db)
        )
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))
        mock_docker_instance.set_compose(RENDERED_YAML)

        response = test_client.post(
            "/api/servers/test-server/convert-to-template",
            json={
                "template_id": template.id,
                "variable_values": VARIABLE_VALUES,
            },
            headers=auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] is None
        assert data["skipped_rebuild"] is True

    def test_convert_with_rebuild(self, test_client, mock_docker_instance):
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(create_test_template(self.db))
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))
        values = {**VARIABLE_VALUES, "name": "test-server"}
        mock_docker_instance.set_compose(RENDERED_YAML.replace("1.20.4", "1.20.1"))
        response = test_client.post(
            "/api/servers/test-server/convert-to-template",
            json={"template_id": template.id, "variable_values": values}, headers=auth_headers(),
        )
        assert_completed_conversion(test_client, response, self.db, template.id, values)

    def test_convert_validation_error(self, test_client):
        """Invalid variable values return 400."""
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(self.db)
        )
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))

        response = test_client.post(
            "/api/servers/test-server/convert-to-template",
            json={
                "template_id": template.id,
                "variable_values": {},
            },
            headers=auth_headers(),
        )
        assert response.status_code == 400

    def test_convert_server_not_found(self, test_client):
        """Non-existent server returns 404."""
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(self.db)
        )

        response = test_client.post(
            "/api/servers/nonexistent/convert-to-template",
            json={
                "template_id": template.id,
                "variable_values": VARIABLE_VALUES,
            },
            headers=auth_headers(),
        )
        assert response.status_code == 404

    def test_convert_template_not_found(self, test_client):
        """Non-existent template returns 404."""
        import asyncio

        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))

        response = test_client.post(
            "/api/servers/test-server/convert-to-template",
            json={
                "template_id": 99999,
                "variable_values": VARIABLE_VALUES,
            },
            headers=auth_headers(),
        )
        assert response.status_code == 404
        assert "模板不存在" in response.json()["detail"]

    def test_convert_stores_snapshot(self, test_client, mock_docker_instance):
        """Verify template snapshot is stored after conversion."""
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(self.db)
        )
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))
        mock_docker_instance.set_compose(RENDERED_YAML)

        test_client.post(
            "/api/servers/test-server/convert-to-template",
            json={
                "template_id": template.id,
                "variable_values": VARIABLE_VALUES,
            },
            headers=auth_headers(),
        )

        # Verify by reading the server record
        async def check_server():
            async with self.db() as session:
                from sqlalchemy import select

                result = await session.execute(
                    select(Server).where(Server.server_id == "test-server")
                )
                server = result.scalar_one()
                assert server.template_id == template.id
                assert server.template_snapshot_json is not None
                snapshot = json.loads(server.template_snapshot_json)
                assert snapshot["template_id"] == template.id
                assert snapshot["template_name"] == "test-template"
                assert snapshot["yaml_template"] == YAML_TEMPLATE
                assert "variable_definitions" in snapshot
                assert "snapshot_time" in snapshot

                assert server.variable_values_json is not None
                values = json.loads(server.variable_values_json)
                assert values == VARIABLE_VALUES

        asyncio.get_event_loop().run_until_complete(check_server())

    def test_convert_server_dir_missing(self, test_client, mock_docker_instance):
        """Server directory not existing returns 404."""
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(self.db)
        )
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))
        mock_docker_instance.exists.return_value = False

        response = test_client.post(
            "/api/servers/test-server/convert-to-template",
            json={
                "template_id": template.id,
                "variable_values": VARIABLE_VALUES,
            },
            headers=auth_headers(),
        )
        assert response.status_code == 404
        assert "服务器目录不存在" in response.json()["detail"]


# ============================================================
# Migration Workflows
# ============================================================


class TestMigrationWorkflows:
    """End-to-end workflow tests for migration between modes."""

    @pytest.fixture(autouse=True)
    async def setup(self, test_db):
        self.db = test_db

    def test_direct_to_template_to_direct(
        self, test_client, mock_docker_instance
    ):
        """Round-trip: direct → template → direct."""
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(self.db)
        )
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))
        mock_docker_instance.set_compose(RENDERED_YAML)

        # Step 1: Convert to template mode
        resp1 = test_client.post(
            "/api/servers/test-server/convert-to-template",
            json={
                "template_id": template.id,
                "variable_values": VARIABLE_VALUES,
            },
            headers=auth_headers(),
        )
        assert resp1.status_code == 200
        assert resp1.json()["skipped_rebuild"] is True

        # Step 2: Convert back to direct mode
        resp2 = test_client.post(
            "/api/servers/test-server/convert-to-direct",
            headers=auth_headers(),
        )
        assert resp2.status_code == 200
        assert resp2.json()["success"] is True

        # Step 3: Verify server is in direct mode
        resp3 = test_client.post(
            "/api/servers/test-server/convert-to-direct",
            headers=auth_headers(),
        )
        assert resp3.status_code == 400  # Already direct

    def test_extract_check_convert_workflow(
        self, test_client, mock_docker_instance
    ):
        """Full workflow: extract variables → check conversion → convert."""
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(self.db)
        )
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))
        mock_docker_instance.set_compose(RENDERED_YAML)

        # Step 1: Extract variables
        resp1 = test_client.post(
            "/api/servers/test-server/extract-variables",
            json={"template_id": template.id},
            headers=auth_headers(),
        )
        assert resp1.status_code == 200
        extracted = resp1.json()["extracted_values"]

        # Step 2: Check if conversion requires rebuild
        resp2 = test_client.post(
            "/api/servers/test-server/check-conversion",
            json={
                "template_id": template.id,
                "variable_values": extracted,
            },
            headers=auth_headers(),
        )
        assert resp2.status_code == 200
        assert resp2.json()["requires_rebuild"] is False

        # Step 3: Convert to template mode
        resp3 = test_client.post(
            "/api/servers/test-server/convert-to-template",
            json={
                "template_id": template.id,
                "variable_values": extracted,
            },
            headers=auth_headers(),
        )
        assert resp3.status_code == 200
        assert resp3.json()["skipped_rebuild"] is True

    def test_convert_with_modified_values_triggers_rebuild(self, test_client, mock_docker_instance):
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(create_test_template(self.db))
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))
        values = {"name": "test-server", "game_port": 30002, "rcon_port": 30003, "game_version": "1.21.0"}
        before = test_client.post(
            "/api/servers/test-server/check-conversion",
            json={"template_id": template.id, "variable_values": values}, headers=auth_headers(),
        )
        assert before.status_code == 200 and before.json()["requires_rebuild"] is True
        assert not current_runtime().task_manager.get_all_tasks()
        response = test_client.post(
            "/api/servers/test-server/convert-to-template",
            json={"template_id": template.id, "variable_values": values}, headers=auth_headers(),
        )
        assert_completed_conversion(test_client, response, self.db, template.id, values)
