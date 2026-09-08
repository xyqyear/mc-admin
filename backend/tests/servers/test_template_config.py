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
      SERVER_PORT: "25565"
      EULA: "TRUE"
      VERSION: "{game_version}"
      MEMORY: "2G"
    volumes:
      - ./data:/data
    restart: unless-stopped
"""


def get_traditional_yaml(
    server_id: str, game_port: int = 25566, rcon_port: int = 25576
):
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
      SERVER_PORT: "25565"
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
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as temp_db:
        database_path = temp_db.name
    database_url = f"sqlite+aiosqlite:///{database_path}"
    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestSessionLocal = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    yield TestSessionLocal

    await engine.dispose()
    Path(database_path).unlink(missing_ok=True)


@pytest.fixture
def test_client(temp_server_path, test_db):
    """Create TestClient with mocked dependencies."""

    async def override_get_db():
        async with test_db() as session:
            yield session

    api_app.dependency_overrides[get_db] = override_get_db

    with (
        patch('app.config.settings.server_path', temp_server_path),
        patch('app.config.settings.master_token', 'test-master-token'),
    ):
        real_mc_manager = DockerMCManager(temp_server_path)
        with (
            patch('app.servers.lifecycle.orchestrators.docker_mc_manager', real_mc_manager),
            patch('app.routers.servers.template_config.docker_mc_manager', real_mc_manager),
            patch('app.servers.port_utils.docker_mc_manager', real_mc_manager),
            patch('app.servers.port_utils.get_system_used_ports', return_value=set()),
            patch('app.servers.lifecycle.orchestrators.log_monitor.start_server', new_callable=AsyncMock),
            patch('app.servers.lifecycle.orchestrators.simple_dns_manager.update', new_callable=AsyncMock),
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
            "variable_definitions": [
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

    @pytest.mark.parametrize("delete_source", [False, True])
    def test_render_preview_uses_server_snapshot(self, test_client, delete_source):
        template_id = create_template(test_client)
        server_id = "snapshot-preview"
        assert create_template_server(test_client, template_id, server_id).status_code == 200
        source_path = f"/api/templates/{template_id}"
        if delete_source:
            assert test_client.delete(source_path, headers=auth_headers()).status_code == 204
        else:
            response = test_client.put(
                source_path,
                json={"yaml_template": YAML_TEMPLATE.replace('MEMORY: "2G"', 'MEMORY: "4G"')},
                headers=auth_headers(),
            )
            assert response.status_code == 200
        response = test_client.post(
            f"/api/servers/{server_id}/template-config/preview",
            json={"variable_values": {
                "name": server_id, "game_port": 25565,
                "rcon_port": 25575, "game_version": "1.21.1",
            }},
            headers=auth_headers(),
        )
        assert response.status_code == 200
        assert 'MEMORY: "2G"' in response.json()["rendered_yaml"]
        assert 'VERSION: "1.21.1"' in response.json()["rendered_yaml"]


async def test_legacy_snapshot_edit_rebuilds_without_requiring_server_port(test_db, temp_server_path):
    from app.background_tasks import BackgroundTaskManager
    from app.minecraft import MCServerStatus
    from app.routers.servers.template_config import (
        TemplateConfigUpdateRequest,
        update_template_config,
    )
    from app.servers.crud import create_server_record, get_active_server_by_id
    from app.templates import (
        StringVariableDefinition,
        TemplateSnapshot,
        VariableDefinition,
    )
    from app.templates.crud import create_template

    manager = DockerMCManager(temp_server_path)
    instance = manager.get_instance("legacy-template")
    legacy = get_traditional_yaml("legacy-template").replace('      SERVER_PORT: "25565"\n', '')
    await instance.create(legacy)
    template_yaml = legacy.replace('MEMORY: "2G"', 'MEMORY: "{memory}"')
    variables: list[VariableDefinition] = [StringVariableDefinition(name="memory", display_name="Memory")]
    async with test_db() as session:
        template = await create_template(session, "legacy", None, template_yaml, variables)
        snapshot = TemplateSnapshot(
            template_id=template.id, template_name="legacy", yaml_template=template_yaml,
            variable_definitions=variables, snapshot_time="2026-09-05T00:00:00Z",
        )
        await create_server_record(session, "legacy-template", template_id=template.id,
                                   template_snapshot_json=snapshot.model_dump_json(),
                                   variable_values_json=json.dumps({"memory": "2G"}))

    tasks = BackgroundTaskManager()
    with (
        patch("app.routers.servers.template_config.docker_mc_manager", manager),
        patch("app.routers.servers.template_config.task_manager", tasks),
        patch("app.servers.rebuild.get_async_session", test_db),
        patch("app.servers.rebuild.docker_mc_manager", manager),
        patch("app.servers.rebuild.check_port_conflicts", AsyncMock(return_value=[])),
        patch.object(instance, "get_status", AsyncMock(return_value=MCServerStatus.EXISTS)),
        patch.object(manager, "get_instance", return_value=instance),
    ):
        async with test_db() as session:
            response = await update_template_config(
                "legacy-template", TemplateConfigUpdateRequest(variable_values={"memory": "3G"}), session,
            )
        future = tasks.get_future(response.task_id)
        assert future is not None
        assert (await future).success

    rendered = await instance.get_compose_file()
    assert 'MEMORY: "3G"' in rendered
    assert "SERVER_PORT" not in rendered
    async with test_db() as session:
        record = await get_active_server_by_id(session, "legacy-template")
        assert record is not None
        assert json.loads(record.variable_values_json or "{}") == {"memory": "3G"}
        assert record.template_snapshot_json == snapshot.model_dump_json()


@pytest.mark.parametrize("failure", [None, "save", "start"])
async def test_rebuild_completion_includes_metadata_save(test_db, temp_server_path, failure):
    from app.background_tasks import BackgroundTaskManager, TaskType
    from app.minecraft import MCServerStatus
    from app.routers.servers.template_config import get_template_config
    from app.servers.configuration import (
        capture_template_snapshot,
        prepare_template_configuration,
    )
    from app.servers.crud import create_server_record, get_active_server_by_id
    from app.servers.rebuild import rebuild_server_task
    from app.templates import StringVariableDefinition
    from app.templates.crud import create_template, save_template

    manager = DockerMCManager(temp_server_path)
    instance = manager.get_instance("metadata-rebuild")
    original = get_traditional_yaml("metadata-rebuild")
    await instance.create(original)
    template_yaml = original.replace('MEMORY: "2G"', 'MEMORY: "{memory}"')
    async with test_db() as db:
        template = await create_template(db, "memory", None, template_yaml, [
            StringVariableDefinition(name="memory", display_name="内存"),
        ])
        configuration = prepare_template_configuration(
            capture_template_snapshot(template), {"memory": "3G"}
        )
        await create_server_record(db, "metadata-rebuild")
        template.yaml_template += "x-source-edited: true\n"
        await save_template(db, template)

    async def start():
        async with test_db() as db:
            record = await get_active_server_by_id(db, "metadata-rebuild")
            assert record is not None
            assert json.loads(record.variable_values_json or "{}") == {"memory": "3G"}
        if failure == "start":
            raise RuntimeError("启动失败")

    tasks = BackgroundTaskManager()
    with (
        patch("app.servers.rebuild.docker_mc_manager", manager),
        patch("app.servers.rebuild.get_async_session", test_db),
        patch("app.servers.rebuild.check_port_conflicts", AsyncMock(return_value=[])),
        patch.object(manager, "get_instance", return_value=instance),
        patch.object(instance, "get_status", AsyncMock(return_value=MCServerStatus.HEALTHY)),
        patch.object(instance, "created", AsyncMock(return_value=False)),
        patch.object(instance, "down", AsyncMock()),
        patch.object(instance, "up", AsyncMock(side_effect=start)) as up,
    ):
        if failure == "save":
            with patch("app.servers.rebuild.save_configuration_metadata", AsyncMock(side_effect=RuntimeError("保存失败"))):
                submitted = tasks.submit(TaskType.SERVER_REBUILD, "重建", rebuild_server_task("metadata-rebuild", configuration))
                result = await submitted.awaitable
        else:
            submitted = tasks.submit(TaskType.SERVER_REBUILD, "重建", rebuild_server_task("metadata-rebuild", configuration))
            result = await submitted.awaitable

    assert result.success is (failure is None)
    assert 'MEMORY: "3G"' in await instance.get_compose_file()
    assert "x-source-edited" not in await instance.get_compose_file()
    assert up.await_count == (0 if failure == "save" else 1)
    async with test_db() as db:
        record = await get_active_server_by_id(db, "metadata-rebuild")
        assert record is not None
        if failure == "save":
            assert record.template_id is None
        else:
            assert json.loads(record.variable_values_json or "{}") == {"memory": "3G"}
            config = await get_template_config("metadata-rebuild", db)
            assert config.has_template_update
            assert config.yaml_template == template_yaml
