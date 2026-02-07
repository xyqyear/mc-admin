"""Integration tests for template migration API endpoints."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import get_db
from app.main import api_app
from app.models import Base, Server, ServerStatus, ServerTemplate
from app.templates.models import serialize_variable_definitions
from app.templates import (
    IntVariableDefinition,
    StringVariableDefinition,
    EnumVariableDefinition,
)

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
def mock_docker_instance():
    """Create a mock Docker MC instance."""
    instance = AsyncMock()
    instance.exists = AsyncMock(return_value=True)
    instance.get_compose_file = AsyncMock(return_value=RENDERED_YAML)
    return instance


@pytest.fixture
def test_client(test_db, mock_docker_instance):
    """Create TestClient with test database and mocked Docker."""

    async def override_get_db():
        async with test_db() as session:
            yield session

    api_app.dependency_overrides[get_db] = override_get_db

    with (
        patch("app.config.settings.master_token", "test-master-token"),
        patch(
            "app.routers.servers.template_migration.docker_mc_manager"
        ) as mock_manager,
    ):
        mock_manager.get_instance.return_value = mock_docker_instance
        client = TestClient(api_app, raise_server_exceptions=False)
        yield client

    api_app.dependency_overrides.pop(get_db, None)


def auth_headers():
    return {"Authorization": "Bearer test-master-token"}


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

    def test_convert_to_direct_success(self, test_client):
        """Convert a template-based server to direct mode."""
        import asyncio

        asyncio.get_event_loop().run_until_complete(self._setup_template_server())

        response = test_client.post(
            "/api/servers/test-server/convert-to-direct",
            headers=auth_headers(),
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

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

    def test_convert_clears_template_fields(self, test_client):
        """Verify template fields are cleared after conversion."""
        import asyncio

        asyncio.get_event_loop().run_until_complete(self._setup_template_server())

        test_client.post(
            "/api/servers/test-server/convert-to-direct",
            headers=auth_headers(),
        )

        # Verify fields are cleared by trying to convert again (should get 400)
        response = test_client.post(
            "/api/servers/test-server/convert-to-direct",
            headers=auth_headers(),
        )
        assert response.status_code == 400


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
        mock_docker_instance.get_compose_file.return_value = RENDERED_YAML

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
        mock_docker_instance.get_compose_file.return_value = (
            "version: '3.8'\nservices:\n  mc:\n    image: test"
        )

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
        mock_docker_instance.get_compose_file.return_value = RENDERED_YAML

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
        mock_docker_instance.get_compose_file.return_value = RENDERED_YAML

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
        mock_docker_instance.get_compose_file.return_value = (
            "version: '3.8'\nservices:\n  mc:\n    image: different"
        )

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
        mock_docker_instance.get_compose_file.return_value = (
            "port: 25565\nname: survival"
        )

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
        mock_docker_instance.get_compose_file.return_value = "ports:\n  - 8081\n  - 8080"

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
        mock_docker_instance.get_compose_file.return_value = RENDERED_YAML

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
        """Convert when YAML differs triggers rebuild."""
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(self.db)
        )
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))
        mock_docker_instance.get_compose_file.return_value = "different: yaml"

        mock_task_result = MagicMock()
        mock_task_result.task_id = "task-123"

        with patch(
            "app.routers.servers.template_migration.task_manager"
        ) as mock_tm:
            mock_tm.submit.return_value = mock_task_result
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
        assert data["task_id"] == "task-123"
        assert data["skipped_rebuild"] is False

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
        mock_docker_instance.get_compose_file.return_value = RENDERED_YAML

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
        mock_docker_instance.get_compose_file.return_value = RENDERED_YAML

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
        mock_docker_instance.get_compose_file.return_value = RENDERED_YAML

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

    def test_convert_with_modified_values_triggers_rebuild(
        self, test_client, mock_docker_instance
    ):
        """Convert with modified values triggers rebuild."""
        import asyncio

        template = asyncio.get_event_loop().run_until_complete(
            create_test_template(self.db)
        )
        asyncio.get_event_loop().run_until_complete(create_test_server(self.db))
        mock_docker_instance.get_compose_file.return_value = RENDERED_YAML

        # Use different values than what's in the compose file
        modified_values = {
            "name": "creative",  # Different name
            "game_port": 30002,
            "rcon_port": 30003,
            "game_version": "1.21.0",
        }

        mock_task_result = MagicMock()
        mock_task_result.task_id = "task-456"

        with patch(
            "app.routers.servers.template_migration.task_manager"
        ) as mock_tm:
            mock_tm.submit.return_value = mock_task_result

            # Check shows rebuild needed
            resp1 = test_client.post(
                "/api/servers/test-server/check-conversion",
                json={
                    "template_id": template.id,
                    "variable_values": modified_values,
                },
                headers=auth_headers(),
            )
            assert resp1.status_code == 200
            assert resp1.json()["requires_rebuild"] is True

            # Convert triggers rebuild
            resp2 = test_client.post(
                "/api/servers/test-server/convert-to-template",
                json={
                    "template_id": template.id,
                    "variable_values": modified_values,
                },
                headers=auth_headers(),
            )
            assert resp2.status_code == 200
            assert resp2.json()["task_id"] == "task-456"
            assert resp2.json()["skipped_rebuild"] is False
