"""
Integration tests for the populate server endpoint.
Tests the full flow: create server -> upload archive -> populate server -> verify files.

Tests handle the background task architecture:
- Endpoint returns task_id immediately
- Task progress is polled via /api/tasks/{task_id}
- Task completion is verified through task status

Note: For actual decompression testing, see test_decompression.py.
The tests here focus on endpoint behavior and mocked task flows.
"""

import asyncio
import random
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.background_tasks import TaskType
from app.main import api_app
from app.minecraft import DockerMCManager


def check_7z_available():
    """Check if 7z command is available."""
    try:
        subprocess.run(["7z"], capture_output=True, check=False)
        return True
    except FileNotFoundError:
        return False


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
def client():
    """Create test client."""
    return TestClient(api_app)


@pytest.fixture
def temp_dirs():
    """Create temporary directories for server and archive paths."""
    with (
        tempfile.TemporaryDirectory(prefix="mc_test_servers_") as server_dir,
        tempfile.TemporaryDirectory(prefix="mc_test_archives_") as archive_dir,
    ):
        yield Path(server_dir), Path(archive_dir)


@pytest.fixture
def mock_settings_and_auth(temp_dirs):
    """Mock settings and authentication."""
    server_path, archive_path = temp_dirs
    real_mc_manager = DockerMCManager(server_path)

    with (
        patch("app.routers.servers.populate.settings") as mock_populate_settings,
        patch("app.routers.archive.settings") as mock_archive_settings,
        patch("app.dependencies.settings") as mock_dep_settings,
        patch("app.utils.decompression.settings") as mock_decomp_settings,
        patch("app.routers.servers.misc.docker_mc_manager", real_mc_manager),
        patch("app.routers.servers.files.docker_mc_manager", real_mc_manager),
        patch("app.routers.servers.create.docker_mc_manager", real_mc_manager),
        patch("app.routers.servers.populate.docker_mc_manager", real_mc_manager),
        patch("app.routers.servers.operations.docker_mc_manager", real_mc_manager),
        patch("app.routers.servers.compose.docker_mc_manager", real_mc_manager),
        patch("app.routers.servers.players.docker_mc_manager", real_mc_manager),
        patch("app.routers.servers.resources.docker_mc_manager", real_mc_manager),
    ):
        # Configure all settings mocks
        for mock_settings_obj in [
            mock_populate_settings,
            mock_archive_settings,
            mock_dep_settings,
            mock_decomp_settings,
        ]:
            mock_settings_obj.server_path = server_path
            mock_settings_obj.archive_path = archive_path
            mock_settings_obj.master_token = "test_master_token"

        yield server_path, archive_path


def wait_for_task_completion(
    client: TestClient, task_id: str, timeout: float = 30.0
) -> dict:
    """
    Poll task status until completion or timeout (sync version for TestClient).

    Note: This only works with tests that mock task execution.
    For actual async task execution, use wait_for_task_completion_async.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        response = client.get(
            f"/api/tasks/{task_id}",
            headers={"Authorization": "Bearer test_master_token"},
        )
        if response.status_code != 200:
            raise RuntimeError(f"Failed to get task status: {response.text}")

        task_data = response.json()
        status = task_data.get("status")

        if status in ["completed", "failed", "cancelled"]:
            return task_data

        time.sleep(0.5)

    raise TimeoutError(f"Task {task_id} did not complete within {timeout}s")


async def wait_for_task_completion_async(
    client: AsyncClient, task_id: str, timeout: float = 30.0
) -> dict:
    """
    Poll task status until completion or timeout (async version).
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
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


@pytest.mark.skipif(not check_7z_available(), reason="7z command not available")
class TestPopulateServerIntegration:
    """Integration tests for populate server endpoint."""

    @pytest.fixture
    async def async_client(self):
        """Create async test client for background task tests."""
        transport = ASGITransport(app=api_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    @pytest.mark.asyncio
    async def test_full_populate_server_flow(
        self, async_client, mock_settings_and_auth
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

        assert create_response.status_code == 200, (
            f"Server creation failed: {create_response.json()}"
        )
        assert "创建成功" in create_response.json()["message"]

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
        assert "填充完成" in task_data.get("message", "")

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

    def test_populate_nonexistent_server(self, client, mock_settings_and_auth):
        """Test populate endpoint with nonexistent server."""
        _, _ = mock_settings_and_auth

        response = client.post(
            "/api/servers/nonexistent_server/populate",
            headers={"Authorization": "Bearer test_master_token"},
            json={"archive_filename": "test.zip"},
        )

        assert response.status_code == 404
        assert "不存在" in response.json()["detail"]

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
      EULA: "TRUE"
      VERSION: "1.20.1"
      MEMORY: "2G"
    volumes:
      - ./data:/data
    restart: unless-stopped
"""

        await async_client.post(
            f"/api/servers/{server_id}",
            headers={"Authorization": "Bearer test_master_token"},
            json={"yaml_content": compose_yaml},
        )

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
      EULA: "TRUE"
      VERSION: "1.20.1"
      MEMORY: "2G"
    volumes:
      - ./data:/data
    restart: unless-stopped
"""

        client.post(
            f"/api/servers/{server_id}",
            headers={"Authorization": "Bearer test_master_token"},
            json={"yaml_content": compose_yaml},
        )

        # Create archive file
        archive_file_path = archive_path / archive_filename
        create_test_minecraft_archive(archive_file_path)

        # Mock the server status to be RUNNING (not allowed)
        with patch("app.routers.servers.populate.docker_mc_manager") as mock_manager:
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
      EULA: "TRUE"
      VERSION: "1.20.1"
      MEMORY: "2G"
    volumes:
      - ./data:/data
    restart: unless-stopped
"""

        await async_client.post(
            f"/api/servers/{server_id}",
            headers={"Authorization": "Bearer test_master_token"},
            json={"yaml_content": compose_yaml},
        )

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
        response = client.post(
            "/api/servers/test_server/populate", json={"archive_filename": "test.zip"}
        )

        # Should return 401 or 422 for missing authentication
        assert response.status_code in [401, 422]


@pytest.mark.skipif(not check_7z_available(), reason="7z command not available")
class TestPopulateProgressTracking:
    """Test progress tracking during server population."""

    @pytest.fixture
    async def async_client(self):
        """Create async test client for background task tests."""
        transport = ASGITransport(app=api_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    @pytest.mark.asyncio
    async def test_progress_updates_during_populate(
        self, async_client, mock_settings_and_auth
    ):
        """Test that task progress updates are tracked during populate."""
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
        assert create_response.status_code == 200, (
            f"Server creation failed: {create_response.json()}"
        )

        # Create archive
        archive_file_path = archive_path / archive_filename
        create_test_minecraft_archive(archive_file_path)

        # Start populate
        response = await async_client.post(
            f"/api/servers/{server_id}/populate",
            headers={"Authorization": "Bearer test_master_token"},
            json={"archive_filename": archive_filename},
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        # Poll for progress updates
        progress_values = []
        messages = []
        start_time = time.time()
        timeout = 30.0

        while time.time() - start_time < timeout:
            task_response = await async_client.get(
                f"/api/tasks/{task_id}",
                headers={"Authorization": "Bearer test_master_token"},
            )
            assert task_response.status_code == 200

            task_data = task_response.json()
            progress = task_data.get("progress")
            message = task_data.get("message")

            if progress is not None and progress not in progress_values:
                progress_values.append(progress)
            if message and message not in messages:
                messages.append(message)

            if task_data["status"] in ["completed", "failed", "cancelled"]:
                break

            await asyncio.sleep(0.3)

        # Verify progress tracking
        assert len(progress_values) >= 1, "Expected at least one progress update"
        assert 100 in progress_values, "Expected final progress of 100%"

        # Verify we got expected step messages
        assert any("填充完成" in m for m in messages), (
            f"Expected completion message, got: {messages}"
        )

        print(f"\nProgress tracking: {progress_values}")
        print(f"Messages: {messages}")


class TestPopulateEndpointIsolated:
    """Test populate endpoint with mocked dependencies for isolation."""

    @pytest.fixture
    def isolated_client(self):
        """Create test client with mocked dependencies."""
        return TestClient(api_app)

    @pytest.fixture
    def mock_task_manager_submit(self):
        """Mock task_manager.submit to return immediately."""
        mock_submit_result = MagicMock()
        mock_submit_result.task_id = "mock-task-id-12345"

        with patch("app.routers.servers.populate.task_manager") as mock_tm:
            mock_tm.submit.return_value = mock_submit_result
            yield mock_tm

    def test_endpoint_returns_task_id(
        self, isolated_client, mock_task_manager_submit, temp_dirs
    ):
        """Test that endpoint returns task_id from task manager."""
        server_path, archive_path = temp_dirs
        real_mc_manager = DockerMCManager(server_path)

        with (
            patch("app.routers.servers.populate.settings") as mock_settings,
            patch("app.dependencies.settings") as mock_dep_settings,
            patch("app.routers.servers.populate.docker_mc_manager", real_mc_manager),
        ):
            mock_settings.server_path = server_path
            mock_settings.archive_path = archive_path
            mock_settings.master_token = "test_master_token"
            mock_dep_settings.master_token = "test_master_token"

            # Create server directory with proper compose file
            server_dir = server_path / "test_server"
            server_dir.mkdir(parents=True)
            compose_content = """services:
  mc:
    image: itzg/minecraft-server:latest
    container_name: mc-test_server
    volumes:
      - ./data:/data
"""
            (server_dir / "docker-compose.yml").write_text(compose_content)
            (server_dir / "data").mkdir()

            response = isolated_client.post(
                "/api/servers/test_server/populate",
                headers={"Authorization": "Bearer test_master_token"},
                json={"archive_filename": "test.zip"},
            )

            assert response.status_code == 200
            data = response.json()
            assert "task_id" in data
            assert data["task_id"] == "mock-task-id-12345"

    def test_endpoint_submits_correct_task_type(
        self, isolated_client, mock_task_manager_submit, temp_dirs
    ):
        """Test that endpoint submits ARCHIVE_EXTRACT task type."""
        server_path, archive_path = temp_dirs
        real_mc_manager = DockerMCManager(server_path)

        with (
            patch("app.routers.servers.populate.settings") as mock_settings,
            patch("app.dependencies.settings") as mock_dep_settings,
            patch("app.routers.servers.populate.docker_mc_manager", real_mc_manager),
        ):
            mock_settings.server_path = server_path
            mock_settings.archive_path = archive_path
            mock_settings.master_token = "test_master_token"
            mock_dep_settings.master_token = "test_master_token"

            # Create server directory with proper compose file
            server_dir = server_path / "test_server"
            server_dir.mkdir(parents=True)
            compose_content = """services:
  mc:
    image: itzg/minecraft-server:latest
    container_name: mc-test_server
    volumes:
      - ./data:/data
"""
            (server_dir / "docker-compose.yml").write_text(compose_content)
            (server_dir / "data").mkdir()

            isolated_client.post(
                "/api/servers/test_server/populate",
                headers={"Authorization": "Bearer test_master_token"},
                json={"archive_filename": "test.zip"},
            )

            # Verify task type
            call_kwargs = mock_task_manager_submit.submit.call_args.kwargs
            assert call_kwargs["task_type"] == TaskType.ARCHIVE_EXTRACT
            assert call_kwargs["server_id"] == "test_server"
            assert call_kwargs["cancellable"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
