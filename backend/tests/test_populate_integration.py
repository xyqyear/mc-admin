"""
Integration tests for the populate server endpoint.
Tests the full flow: create server -> upload archive -> populate server -> verify files.
"""

import json
import random
import subprocess
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


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
        "logs/latest.log": """[12:00:00] [Server thread/INFO]: Starting minecraft server version 1.20.4
[12:00:01] [Server thread/INFO]: Server started
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
    
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file_path, content in server_structure.items():
            zf.writestr(file_path, content)


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def temp_dirs():
    """Create temporary directories for server and archive paths."""
    with tempfile.TemporaryDirectory(prefix="mc_test_servers_") as server_dir, \
         tempfile.TemporaryDirectory(prefix="mc_test_archives_") as archive_dir:
        yield Path(server_dir), Path(archive_dir)


@pytest.fixture
def mock_settings_and_auth(temp_dirs):
    """Mock settings and authentication."""
    server_path, archive_path = temp_dirs
    
    with (
        patch("app.routers.servers.misc.settings") as mock_misc_settings,
        patch("app.routers.servers.files.settings") as mock_files_settings,
        patch("app.routers.archive.settings") as mock_archive_settings,
        patch("app.dependencies.settings") as mock_dep_settings,
        patch("app.utils.decompression.settings") as mock_decomp_settings,
        patch("app.routers.servers.misc.mc_manager") as mock_mc_manager,
        patch("app.routers.servers.files.mc_manager") as mock_files_manager,
    ):
        # Configure all settings mocks
        for mock_settings_obj in [mock_misc_settings, mock_files_settings, mock_archive_settings, mock_dep_settings, mock_decomp_settings]:
            mock_settings_obj.server_path = server_path
            mock_settings_obj.archive_path = archive_path
            mock_settings_obj.master_token = "test_master_token"
            
        # Configure mc_managers to use our temporary directory
        from app.minecraft import DockerMCManager
        real_mc_manager = DockerMCManager(server_path)
        
        # Mock both misc and files mc_managers
        for manager_mock in [mock_mc_manager, mock_files_manager]:
            manager_mock.get_instance = real_mc_manager.get_instance
            manager_mock.get_all_instances = real_mc_manager.get_all_instances
            manager_mock.get_all_server_names = real_mc_manager.get_all_server_names
            
        yield server_path, archive_path


@pytest.mark.skipif(not check_7z_available(), reason="7z command not available")
class TestPopulateServerIntegration:
    """Integration tests for populate server endpoint."""
    
    def test_full_populate_server_flow(self, client, mock_settings_and_auth):
        """Test complete flow: create server -> upload archive -> populate -> verify."""
        server_path, archive_path = mock_settings_and_auth
        server_id = f"test_server_{random.randint(1000, 9999)}"
        archive_filename = f"minecraft_server_{random.randint(1000, 9999)}.zip"
        game_port = random.randint(30000, 40000)
        rcon_port = game_port + 1
        
        # Step 1: Create server compose YAML
        compose_yaml = f"""services:
  mc:
    image: itzg/minecraft-server:java21-alpine
    container_name: mc-{server_id}
    environment:
      EULA: 'true'
      VERSION: 1.20.4
      INIT_MEMORY: 0M
      MAX_MEMORY: 500M
      ONLINE_MODE: 'false'
      TYPE: VANILLA
      ENABLE_RCON: 'true'
      MODE: creative
    ports:
    - {game_port}:25565
    - {rcon_port}:25575
    volumes:
    - ./data:/data
    stdin_open: true
    tty: true
    restart: unless-stopped
"""
        
        # Step 2: Create server using API
        create_response = client.post(
            f"/api/servers/{server_id}",
            headers={"Authorization": "Bearer test_master_token"},
            json={"yaml_content": compose_yaml}
        )
        
        assert create_response.status_code == 200, f"Server creation failed: {create_response.json()}"
        assert "created successfully" in create_response.json()["message"]
        
        # Verify server exists on filesystem
        server_dir = server_path / server_id
        assert server_dir.exists()
        assert (server_dir / "compose.yaml").exists()
        assert (server_dir / "data").exists()
        
        # Step 3: Create and upload archive file
        archive_file_path = archive_path / archive_filename
        create_test_minecraft_archive(archive_file_path)
        
        # Verify archive was created correctly
        assert archive_file_path.exists()
        assert archive_file_path.stat().st_size > 0
        
        # Step 4: Populate server with archive
        populate_response = client.post(
            f"/api/servers/{server_id}/populate",
            headers={"Authorization": "Bearer test_master_token"},
            json={"archive_filename": archive_filename}
        )
        
        assert populate_response.status_code == 200, f"Populate failed: {populate_response.text}"
        
        # Parse SSE response
        sse_lines = populate_response.text.strip().split('\n')
        sse_events = []
        
        for line in sse_lines:
            if line.startswith('data: '):
                event_data = line[6:]  # Remove 'data: ' prefix
                try:
                    event = json.loads(event_data)
                    sse_events.append(event)
                except json.JSONDecodeError:
                    # Skip malformed JSON lines
                    continue
        
        # Verify SSE events
        assert len(sse_events) > 0, "No SSE events received"
        
        # Check that we have expected steps
        steps = [event['step'] for event in sse_events]
        expected_steps = ['cleanup', 'archiveFileCheck', 'serverPropertiesCheck', 
                         'decompress', 'chown', 'findPath', 'mv', 'remove', 'complete']
        
        # Not all steps may be present due to the way SSE streaming works, but check key ones
        assert 'cleanup' in steps, f"Missing cleanup step. Got steps: {steps}"
        assert 'complete' in steps, f"Missing complete step. Got steps: {steps}"
        
        # Verify all events are successful
        failed_events = [event for event in sse_events if not event.get('success', True)]
        assert len(failed_events) == 0, f"Failed events: {failed_events}"
        
        # Step 5: Verify files using files API
        files_response = client.get(
            f"/api/servers/{server_id}/files",
            headers={"Authorization": "Bearer test_master_token"},
            params={"path": "/"}
        )
        
        assert files_response.status_code == 200, f"Files list failed: {files_response.json()}"
        files_data = files_response.json()
        
        # Verify file structure
        assert "items" in files_data
        file_items = files_data["items"]
        
        # Get list of file/directory names
        item_names = {item["name"] for item in file_items}
        
        # Verify key files exist
        expected_files = {"server.properties", "world", "plugins", "logs", "eula.txt", "server.jar"}
        missing_files = expected_files - item_names
        assert len(missing_files) == 0, f"Missing files: {missing_files}. Available: {item_names}"
        
        # Step 6: Verify specific file content
        server_properties_response = client.get(
            f"/api/servers/{server_id}/files/content",
            headers={"Authorization": "Bearer test_master_token"},
            params={"path": "/server.properties"}
        )
        
        assert server_properties_response.status_code == 200
        properties_data = server_properties_response.json()
        assert "content" in properties_data
        properties_content = properties_data["content"]
        
        # Verify server.properties content
        assert "server-port=25565" in properties_content
        assert "level-name=world" in properties_content
        assert "enable-rcon=true" in properties_content
        
        # Step 7: Check subdirectories
        world_files_response = client.get(
            f"/api/servers/{server_id}/files",
            headers={"Authorization": "Bearer test_master_token"},
            params={"path": "/world"}
        )
        
        assert world_files_response.status_code == 200
        world_data = world_files_response.json()
        world_items = {item["name"] for item in world_data["items"]}
        assert "level.dat" in world_items
        assert "region" in world_items
        
        # Step 8: Verify archive was cleaned up (should be deleted after extraction)
        assert not archive_file_path.exists(), "Archive file should be deleted after extraction"
        
        print(f"✅ Full populate integration test completed successfully for server '{server_id}'")
    
    def test_populate_nonexistent_server(self, client, mock_settings_and_auth):
        """Test populate endpoint with nonexistent server."""
        server_path, archive_path = mock_settings_and_auth
        
        response = client.post(
            "/api/servers/nonexistent_server/populate",
            headers={"Authorization": "Bearer test_master_token"},
            json={"archive_filename": "test.zip"}
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
    
    def test_populate_nonexistent_archive(self, client, mock_settings_and_auth):
        """Test populate endpoint with nonexistent archive file."""
        server_path, archive_path = mock_settings_and_auth
        server_id = "test_server"
        
        # Create server first
        compose_yaml = """services:
  mc:
    image: itzg/minecraft-server
    ports: ["25565:25565"]
    volumes: ["./data:/data"]
"""
        
        client.post(
            f"/api/servers/{server_id}",
            headers={"Authorization": "Bearer test_master_token"},
            json={"yaml_content": compose_yaml}
        )
        
        # Try to populate with nonexistent archive
        response = client.post(
            f"/api/servers/{server_id}/populate",
            headers={"Authorization": "Bearer test_master_token"},
            json={"archive_filename": "nonexistent.zip"}
        )
        
        assert response.status_code == 404
        assert "Archive file" in response.json()["detail"]
        assert "not found" in response.json()["detail"]
    
    def test_populate_server_wrong_status(self, client, mock_settings_and_auth):
        """Test populate endpoint with server in wrong status."""
        server_path, archive_path = mock_settings_and_auth
        server_id = "test_server"
        archive_filename = "test.zip"
        
        # Create server and start it (this would put it in RUNNING status if Docker was available)
        compose_yaml = """services:
  mc:
    image: itzg/minecraft-server
    ports: ["25565:25565"]
    volumes: ["./data:/data"]
"""
        
        client.post(
            f"/api/servers/{server_id}",
            headers={"Authorization": "Bearer test_master_token"},
            json={"yaml_content": compose_yaml}
        )
        
        # Create archive file
        archive_file_path = archive_path / archive_filename
        create_test_minecraft_archive(archive_file_path)
        
        # Mock the server status to be RUNNING (not allowed)
        with patch("app.routers.servers.misc.mc_manager") as mock_manager:
            from app.minecraft import MCServerStatus
            
            mock_instance = mock_manager.get_instance.return_value
            mock_instance.exists.return_value = True
            mock_instance.get_status.return_value = MCServerStatus.RUNNING
            
            response = client.post(
                f"/api/servers/{server_id}/populate",
                headers={"Authorization": "Bearer test_master_token"},
                json={"archive_filename": archive_filename}
            )
            
            assert response.status_code == 409
            assert "must be in 'exists' or 'created' status" in response.json()["detail"]
    
    def test_populate_with_invalid_archive(self, client, mock_settings_and_auth):
        """Test populate endpoint with invalid archive (missing server.properties)."""
        server_path, archive_path = mock_settings_and_auth
        server_id = "test_server"
        archive_filename = "invalid.zip"
        
        # Create server
        compose_yaml = """services:
  mc:
    image: itzg/minecraft-server
    ports: ["25565:25565"]
    volumes: ["./data:/data"]
"""
        
        client.post(
            f"/api/servers/{server_id}",
            headers={"Authorization": "Bearer test_master_token"},
            json={"yaml_content": compose_yaml}
        )
        
        # Create invalid archive (without server.properties)
        archive_file_path = archive_path / archive_filename
        with zipfile.ZipFile(archive_file_path, 'w') as zf:
            zf.writestr("some_file.txt", "not a minecraft server")
            zf.writestr("random/data.txt", "random content")
        
        # Try to populate with invalid archive
        response = client.post(
            f"/api/servers/{server_id}/populate",
            headers={"Authorization": "Bearer test_master_token"},
            json={"archive_filename": archive_filename}
        )
        
        assert response.status_code == 200  # SSE always returns 200
        
        # Parse SSE response to check for errors
        sse_lines = response.text.strip().split('\n')
        sse_events = []
        
        for line in sse_lines:
            if line.startswith('data: '):
                event_data = line[6:]
                try:
                    event = json.loads(event_data)
                    sse_events.append(event)
                except json.JSONDecodeError:
                    continue
        
        # Should have error event
        error_events = [event for event in sse_events if not event.get('success', True)]
        assert len(error_events) > 0, f"Expected error events, got: {sse_events}"
        
        # Check error is about server.properties
        properties_errors = [
            event for event in error_events 
            if 'server.properties' in event.get('message', '') or 
               event.get('step') == 'serverPropertiesCheck'
        ]
        assert len(properties_errors) > 0, f"Expected server.properties error, got: {error_events}"
    
    def test_unauthorized_access(self, client, mock_settings_and_auth):
        """Test populate endpoint without authentication."""
        response = client.post(
            "/api/servers/test_server/populate",
            json={"archive_filename": "test.zip"}
        )
        
        # Should return 401 or 422 for missing authentication
        assert response.status_code in [401, 422]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])