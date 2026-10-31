"""
Integration tests for the populate server endpoint.
Tests the full flow: create server -> upload archive -> populate server -> verify files.

Tests handle the background task architecture:
- Endpoint returns task_id immediately
- Task progress is polled via /api/tasks/{task_id}
- Task completion is verified through task status
"""
import asyncio
import random
import tempfile
import time
import zipfile
from contextlib import aclosing
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import api_app
from app.minecraft import DockerMCManager
from app.operations.journal import OperationJournal
from app.operations.models import OperationJournalEntry
from app.runtime_resources import current_runtime
from app.servers.models import Server
from tests.support.runtime import patch_runtime_resource, patch_settings
from tests.support.tasks import task_result


@pytest.fixture(autouse=True)
def uncreated_containers():
    with patch(
        "app.minecraft.docker.manager.ComposeManager.created",
        AsyncMock(return_value=False),
    ):
        yield


def create_test_minecraft_archive(archive_path: Path) -> None:
    """Create a test Minecraft server archive with proper structure."""
    # Create test content for a Minecraft server
    server_structure = {
        "server.properties": """# Minecraft server properties
server-port=25565
level-name=world
gamemode=survival
difficulty=easy
max-players=20
online-mode=false
enable-rcon=true
rcon.port=25575
rcon.password=minecraft
""",
        "world/level.dat": "fake_world_data_here",
        "world/region/r.0.0.mca": "fake_region_data",
        "plugins/essentials.jar": "fake_plugin_jar_content",
        "plugins/config.yml": """# Plugin config
spawn-on-join: true
teleport-safety: true
""",
        "ops.json": "[]",
        "whitelist.json": "[]",
        "banned-players.json": "[]",
        "banned-ips.json": "[]",
        "usercache.json": "{}",
        "servericon.png": "fake_png_data",
        "eula.txt": "eula=true",
        "server.jar": "fake_minecraft_server_jar_content" * 100,  # Larger file
    }

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path, content in server_structure.items():
            zf.writestr(file_path, content)


@pytest.fixture
def client(database):
    with TestClient(api_app) as client:
        yield client


@pytest.fixture
def temp_dirs():
    """Create temporary directories for server and archive paths."""
    with (
        tempfile.TemporaryDirectory(prefix="mc_test_servers_") as server_dir,
        tempfile.TemporaryDirectory(prefix="mc_test_archives_") as archive_dir,
    ):
        yield Path(server_dir), Path(archive_dir)


@pytest.fixture
def mock_settings_and_auth(temp_dirs, database):
    current_runtime().journal = OperationJournal(database.session_factory)
    server_path, archive_path = temp_dirs
    with (
        patch_settings() as settings,
        patch_runtime_resource('docker_mc_manager', DockerMCManager(server_path)),
        patch("app.servers.port_utils.get_system_used_ports", return_value=set()),
        patch.object(current_runtime().log_monitor, 'start_server', new_callable=AsyncMock),
        patch.object(current_runtime().dns_manager, 'update', new_callable=AsyncMock),
    ):
        settings.server_path = server_path
        settings.archive_path = archive_path
        settings.master_token = "test_master_token"
        yield server_path, archive_path


async def wait_for_task_completion_async(
    client: AsyncClient, task_id: str, timeout: float = 30.0
) -> dict:
    """
    Poll task status until completion or timeout (async version).
    """
    start_time = time.monotonic()
    while time.monotonic() - start_time < timeout:
        response = await client.get(
            f"/api/tasks/{task_id}",
            headers={"Authorization": "Bearer test_master_token"},
        )
        if response.status_code != 200:
            raise RuntimeError(f"Failed to get task status: {response.text}")

        task_data = response.json()
        status = task_data.get("status")

        if status in ["completed", "failed", "cancelled"]:
            return task_data

        await asyncio.sleep(0.5)

    raise TimeoutError(f"Task {task_id} did not complete within {timeout}s")


class TestPopulateServerIntegration:
    """Integration tests for populate server endpoint."""

    @pytest.fixture
    async def async_client(self):
        """Create async test client for background task tests."""
        transport = ASGITransport(app=api_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    @pytest.mark.binary("7z")
    @pytest.mark.asyncio
    async def test_full_populate_server_flow(
        self, async_client, mock_settings_and_auth, db_session_factory
    ):
        """Test complete flow: create server -> upload archive -> populate -> verify."""
        server_path, archive_path = mock_settings_and_auth
        server_id = f"test_server_{random.randint(1000, 9999)}"
        archive_filename = f"minecraft_server_{random.randint(1000, 9999)}.zip"
        game_port = random.randint(30000, 40000)
        rcon_port = game_port + 1

        # Step 1: Create server compose YAML
        compose_yaml = f"""version: '3.8'
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

        # Step 2: Create server using API
        create_response = await async_client.post(
            f"/api/servers/{server_id}",
            headers={"Authorization": "Bearer test_master_token"},
            json={"yaml_content": compose_yaml},
        )

        assert create_response.status_code == 202, create_response.text
        creation = await wait_for_task_completion_async(async_client, create_response.json()["task_id"])
        assert creation["status"] == "completed", creation
        assert creation["result"]["server_id"] == server_id

        # Verify server exists on filesystem
        server_dir = server_path / server_id
        assert server_dir.exists()
        assert (server_dir / "docker-compose.yml").exists()
        assert (server_dir / "data").exists()

        # Step 3: Create and upload archive file
        archive_file_path = archive_path / archive_filename
        create_test_minecraft_archive(archive_file_path)

        # Verify archive was created correctly
        assert archive_file_path.exists()
        assert archive_file_path.stat().st_size > 0

        # Step 4: Populate server with archive (returns task_id)
        populate_response = await async_client.post(
            f"/api/servers/{server_id}/populate",
            headers={"Authorization": "Bearer test_master_token"},
            json={"archive_filename": archive_filename},
        )

        assert populate_response.status_code == 200, (
            f"Populate failed: {populate_response.text}"
        )

        # Parse JSON response - should contain task_id
        populate_data = populate_response.json()
        assert "task_id" in populate_data, (
            f"Expected task_id in response: {populate_data}"
        )
        task_id = populate_data["task_id"]

        # Step 5: Wait for task to complete
        task_data = await wait_for_task_completion_async(async_client, task_id)

        assert task_data["status"] == "completed", (
            f"Task failed: {task_data.get('error')}"
        )
        assert task_data["progress"] == 100
        assert task_data["task_type"] == "archive_extract"
        assert task_data["server_id"] == server_id
        assert task_data["cancellable"] is False
        assert "填充完成" in task_data.get("message", "")
        async with db_session_factory() as session:
            for identity, kind in ((create_response.json()["task_id"], "server_create"), (task_id, "archive_extract")):
                operation = await session.get(OperationJournalEntry, identity)
                assert operation is not None
                assert operation.kind == kind and operation.state == "succeeded"
                assert operation.writers_stopped and operation.ended_at is not None

        # Step 6: Verify files using files API
        files_response = await async_client.get(
            f"/api/servers/{server_id}/files",
            headers={"Authorization": "Bearer test_master_token"},
            params={"path": "/"},
        )

        assert files_response.status_code == 200, (
            f"Files list failed: {files_response.json()}"
        )
        files_data = files_response.json()

        # Verify file structure
        assert "items" in files_data
        file_items = files_data["items"]

        # Get list of file/directory names
        item_names = {item["name"] for item in file_items}

        # Verify key files exist
        expected_files = {
            "server.properties",
            "world",
            "plugins",
            "eula.txt",
            "server.jar",
        }
        missing_files = expected_files - item_names
        assert len(missing_files) == 0, (
            f"Missing files: {missing_files}. Available: {item_names}"
        )

        # Step 7: Verify specific file content
        server_properties_response = await async_client.get(
            f"/api/servers/{server_id}/files/content",
            headers={"Authorization": "Bearer test_master_token"},
            params={"path": "/server.properties"},
        )

        assert server_properties_response.status_code == 200
        properties_data = server_properties_response.json()
        assert "content" in properties_data
        properties_content = properties_data["content"]

        # Verify server.properties content
        assert "server-port=25565" in properties_content
        assert "level-name=world" in properties_content
        assert "enable-rcon=true" in properties_content

        # Step 8: Check subdirectories
        world_files_response = await async_client.get(
            f"/api/servers/{server_id}/files",
            headers={"Authorization": "Bearer test_master_token"},
            params={"path": "/world"},
        )

        assert world_files_response.status_code == 200
        world_data = world_files_response.json()
        world_items = {item["name"] for item in world_data["items"]}
        assert "level.dat" in world_items
        assert "region" in world_items

        # Step 9: Verify archive was cleaned up (should be deleted after extraction)
        assert not archive_file_path.exists(), (
            "Archive file should be deleted after extraction"
        )

        print(
            f"Full populate integration test completed successfully for server '{server_id}'"
        )

    async def test_populate_nonexistent_server(
        self, async_client, mock_settings_and_auth, db_session_factory
    ):
        server_path, archive_path = mock_settings_and_auth
        archive = archive_path / "test.zip"
        create_test_minecraft_archive(archive)
        original_archive = archive.read_bytes()

        response = await async_client.post(
            "/api/servers/nonexistent_server/populate",
            headers={"Authorization": "Bearer test_master_token"},
            json={"archive_filename": "test.zip"},
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "服务器尚未登记；已有目录需要先显式接管"}
        assert current_runtime().task_manager.get_all_tasks() == []
        async with db_session_factory() as session:
            assert await session.scalar(select(Server.id)) is None
            assert await session.scalar(select(OperationJournalEntry.operation_id)) is None
        assert list(server_path.iterdir()) == []
        assert list(archive_path.iterdir()) == [archive]
        assert archive.read_bytes() == original_archive

    @pytest.mark.asyncio
    async def test_populate_nonexistent_archive(
        self, async_client, mock_settings_and_auth
    ):
        """Test populate endpoint with nonexistent archive file."""
        _, _ = mock_settings_and_auth
        server_id = "test_server"

        # Create server first
        compose_yaml = """version: '3.8'
services:
  mc:
    image: itzg/minecraft-server:latest
    container_name: mc-test_server
    ports:
      - "25565:25565"
      - "25575:25575"
    environment:
      SERVER_PORT: "25565"
      EULA: "TRUE"
      VERSION: "1.20.1"
      MEMORY: "2G"
    volumes:
      - ./data:/data
    restart: unless-stopped
"""

        create_response = await async_client.post(
            f"/api/servers/{server_id}",
            headers={"Authorization": "Bearer test_master_token"},
            json={"yaml_content": compose_yaml},
        )
        assert create_response.status_code == 202, create_response.text
        creation = await wait_for_task_completion_async(async_client, create_response.json()["task_id"])
        assert creation["status"] == "completed", creation
        assert creation["result"]["server_id"] == server_id

        # Try to populate with nonexistent archive
        response = await async_client.post(
            f"/api/servers/{server_id}/populate",
            headers={"Authorization": "Bearer test_master_token"},
            json={"archive_filename": "nonexistent.zip"},
        )

        # Endpoint returns 200 with task_id, task will fail
        assert response.status_code == 200
        task_id = response.json()["task_id"]

        # Wait for task to complete (should fail)
        task_data = await wait_for_task_completion_async(async_client, task_id)

        assert task_data["status"] == "failed"
        assert "压缩包不存在" in task_data.get("error", "")

    def test_populate_server_wrong_status(self, client, mock_settings_and_auth):
        """Test populate endpoint with server in wrong status."""
        _, archive_path = mock_settings_and_auth
        server_id = "test_server"
        archive_filename = "test.zip"

        # Create server and start it (this would put it in RUNNING status if Docker was available)
        compose_yaml = """version: '3.8'
services:
  mc:
    image: itzg/minecraft-server:latest
    container_name: mc-test_server
    ports:
      - "25565:25565"
      - "25575:25575"
    environment:
      SERVER_PORT: "25565"
      EULA: "TRUE"
      VERSION: "1.20.1"
      MEMORY: "2G"
    volumes:
      - ./data:/data
    restart: unless-stopped
"""

        create_response = client.post(
            f"/api/servers/{server_id}",
            headers={"Authorization": "Bearer test_master_token"},
            json={"yaml_content": compose_yaml},
        )
        assert task_result(client, create_response)["server_id"] == server_id

        # Create archive file
        archive_file_path = archive_path / archive_filename
        create_test_minecraft_archive(archive_file_path)

        # Mock the server status to be RUNNING (not allowed)
        with patch_runtime_resource('docker_mc_manager') as mock_manager:
            from unittest.mock import AsyncMock

            from app.minecraft import MCServerStatus

            mock_instance = mock_manager.get_instance.return_value
            mock_instance.exists = AsyncMock(return_value=True)
            mock_instance.get_status = AsyncMock(return_value=MCServerStatus.RUNNING)

            response = client.post(
                f"/api/servers/{server_id}/populate",
                headers={"Authorization": "Bearer test_master_token"},
                json={"archive_filename": archive_filename},
            )

            assert response.status_code == 409
            assert "必须处于 'exists' 或 'created' 状态" in response.json()["detail"]

    @pytest.mark.binary("7z")
    @pytest.mark.asyncio
    async def test_populate_with_invalid_archive(
        self, async_client, mock_settings_and_auth
    ):
        """Test populate endpoint with invalid archive (missing server.properties)."""
        _, archive_path = mock_settings_and_auth
        server_id = "test_server"
        archive_filename = "invalid.zip"

        # Create server
        compose_yaml = """version: '3.8'
services:
  mc:
    image: itzg/minecraft-server:latest
    container_name: mc-test_server
    ports:
      - "25565:25565"
      - "25575:25575"
    environment:
      SERVER_PORT: "25565"
      EULA: "TRUE"
      VERSION: "1.20.1"
      MEMORY: "2G"
    volumes:
      - ./data:/data
    restart: unless-stopped
"""

        create_response = await async_client.post(
            f"/api/servers/{server_id}",
            headers={"Authorization": "Bearer test_master_token"},
            json={"yaml_content": compose_yaml},
        )
        assert create_response.status_code == 202, create_response.text
        creation = await wait_for_task_completion_async(async_client, create_response.json()["task_id"])
        assert creation["status"] == "completed", creation
        assert creation["result"]["server_id"] == server_id

        # Create invalid archive (without server.properties)
        archive_file_path = archive_path / archive_filename
        with zipfile.ZipFile(archive_file_path, "w") as zf:
            zf.writestr("some_file.txt", "not a minecraft server")
            zf.writestr("random/data.txt", "random content")

        # Try to populate with invalid archive
        response = await async_client.post(
            f"/api/servers/{server_id}/populate",
            headers={"Authorization": "Bearer test_master_token"},
            json={"archive_filename": archive_filename},
        )

        # Endpoint returns 200 with task_id, task will fail
        assert response.status_code == 200
        task_id = response.json()["task_id"]

        # Wait for task to complete (should fail)
        task_data = await wait_for_task_completion_async(async_client, task_id)

        assert task_data["status"] == "failed"
        assert "压缩包中未找到server.properties文件" in task_data.get("error", "")

    def test_unauthorized_access(self, client, mock_settings_and_auth):
        """Test populate endpoint without authentication."""
        _ = mock_settings_and_auth
        with patch.object(current_runtime().task_manager, "submit_durable", new_callable=AsyncMock) as submit:
            response = client.post(
                "/api/servers/test_server/populate", json={"archive_filename": "test.zip"}
            )

        assert response.status_code == 401
        submit.assert_not_called()


class TestPopulateProgressTracking:
    """Test progress tracking during server population."""

    @pytest.fixture
    async def async_client(self):
        """Create async test client for background task tests."""
        transport = ASGITransport(app=api_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    @pytest.mark.binary("7z")
    @pytest.mark.asyncio
    async def test_progress_updates_during_populate(
        self, async_client, mock_settings_and_auth, monkeypatch
    ):
        """Test that task progress updates are tracked during populate."""
        from app.files import population

        server_path, archive_path = mock_settings_and_auth
        server_id = f"test_server_{random.randint(1000, 9999)}"
        archive_filename = f"progress_test_{random.randint(1000, 9999)}.zip"

        # Create server
        compose_yaml = f"""version: '3.8'
services:
  mc:
    image: itzg/minecraft-server:latest
    container_name: mc-{server_id}
    ports:
      - "25565:25565"
      - "25575:25575"
    environment:
      SERVER_PORT: "25565"
      EULA: "TRUE"
      VERSION: "1.20.1"
      MEMORY: "2G"
    volumes:
      - ./data:/data
"""

        create_response = await async_client.post(
            f"/api/servers/{server_id}",
            headers={"Authorization": "Bearer test_master_token"},
            json={"yaml_content": compose_yaml},
        )
        assert create_response.status_code == 202, create_response.text
        creation = await wait_for_task_completion_async(async_client, create_response.json()["task_id"])
        assert creation["status"] == "completed", creation
        assert creation["result"]["server_id"] == server_id

        # Create archive
        archive_file_path = archive_path / archive_filename
        create_test_minecraft_archive(archive_file_path)

        entered = asyncio.Event()
        release = asyncio.Event()
        original_extract = population.extract_minecraft_server

        async def gated_extract(*args, **kwargs):
            async with aclosing(original_extract(*args, **kwargs)) as events:
                async for event in events:
                    yield event
                    if event.message == "验证server.properties...":
                        entered.set()
                        await release.wait()

        monkeypatch.setattr(population, "extract_minecraft_server", gated_extract)
        response = await async_client.post(
            f"/api/servers/{server_id}/populate",
            headers={"Authorization": "Bearer test_master_token"},
            json={"archive_filename": archive_filename},
        )
        assert response.status_code == 200
        task_id = response.json()["task_id"]
        try:
            async with asyncio.timeout(5):
                await entered.wait()
            task_response = await async_client.get(
                f"/api/tasks/{task_id}",
                headers={"Authorization": "Bearer test_master_token"},
            )
            assert task_response.status_code == 200
            task_data = task_response.json()
            assert task_data["status"] == "running"
            assert task_data["progress"] == 5
            assert task_data["message"] == "验证server.properties..."
            assert task_data["result"] is None
        finally:
            release.set()
            completed = await wait_for_task_completion_async(async_client, task_id)
        assert completed["status"] == "completed", completed
        assert completed["progress"] == 100
        assert "填充完成" in completed["message"]
        assert (server_path / server_id / "data/world/level.dat").read_bytes() == b"fake_world_data_here"
