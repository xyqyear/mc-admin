"""
Comprehensive integration tests for the create server endpoint.
Covers port conflict detection, YAML validation, and server creation scenarios.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import api_app

YAML_TEMPLATE = """
version: '3.8'
services:
  mc:
    image: itzg/minecraft-server:latest
    container_name: mc-{server_name}
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

# Pre-defined YAML configurations for different test scenarios
VALID_YAML_BASIC = YAML_TEMPLATE.format(
    server_name="test-basic", game_port=25565, rcon_port=25575
).strip()

VALID_YAML_DIFFERENT_PORTS = YAML_TEMPLATE.format(
    server_name="test-different", game_port=25566, rcon_port=25576
).strip()

INVALID_YAML_NO_VERSION = """
version: '3.8'
services:
  mc:
    image: itzg/minecraft-server:latest
    container_name: mc-invalid-no-version
    ports:
      - "25568:25565"
      - "25579:25575"
    environment:
      EULA: "TRUE"
      MEMORY: "2G"
    volumes:
      - ./data:/data
    restart: unless-stopped
""".strip()

INVALID_YAML_MISSING_GAME_PORT = """
version: '3.8'
services:
  mc:
    image: itzg/minecraft-server:latest
    container_name: mc-invalid-missing-port
    ports:
      - "25575:25575"
    environment:
      EULA: "TRUE"
      VERSION: "1.20.1"
      MEMORY: "2G"
    volumes:
      - ./data:/data
    restart: unless-stopped
""".strip()

INVALID_YAML_MISSING_RCON_PORT = """
version: '3.8'
services:
  mc:
    image: itzg/minecraft-server:latest
    container_name: mc-invalid-missing-rcon
    ports:
      - "25565:25565"
    environment:
      EULA: "TRUE"
      VERSION: "1.20.1"
      MEMORY: "2G"
    volumes:
      - ./data:/data
    restart: unless-stopped
""".strip()

INVALID_YAML_SYNTAX = """
version: '3.8'
services:
  mc:
    image: itzg/minecraft-server:latest
    invalid: yaml: syntax: [
""".strip()

INVALID_YAML_WRONG_IMAGE = """
version: '3.8'
services:
  mc:
    image: nginx:latest
    container_name: mc-wrong-image
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
""".strip()

INVALID_YAML_WRONG_CONTAINER_NAME = """
version: '3.8'
services:
  mc:
    image: itzg/minecraft-server:latest
    container_name: wrong-container-name
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
""".strip()


@pytest.fixture
def temp_server_path():
    """Create a temporary directory for server files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def test_client_with_temp_path(temp_server_path):
    """Create TestClient with temporary server path."""
    from app.minecraft import DockerMCManager

    # Patch settings and create real mc_manager with temp path
    with patch("app.config.settings.server_path", temp_server_path):
        with patch("app.config.settings.master_token", "test-master-token"):
            # Create real mc_manager with temporary server path
            real_mc_manager = DockerMCManager(temp_server_path)
            with patch("app.routers.servers.create.mc_manager", real_mc_manager):
                client = TestClient(api_app)
                yield client


def generate_yaml(
    server_name: str, game_port: int = 25565, rcon_port: int = 25575
) -> str:
    """Generate YAML with specific server name and ports."""
    return YAML_TEMPLATE.format(
        server_name=server_name, game_port=game_port, rcon_port=rcon_port
    ).strip()


class TestCreateServerSuccess:
    """Test successful server creation scenarios."""

    def test_successful_server_creation(self, test_client_with_temp_path):
        """Test successful server creation with unique ports."""
        yaml_content = generate_yaml("test-server", 25565, 25575)

        response = test_client_with_temp_path.post(
            "/api/servers/test-server",
            json={"yaml_content": yaml_content},
            headers={"Authorization": "Bearer test-master-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Server 'test-server' created successfully"
        assert data["game_port"] == 25565
        assert data["rcon_port"] == 25575

    def test_no_conflicts_with_different_ports(self, test_client_with_temp_path):
        """Test that servers with different ports can be created successfully."""
        # Create first server
        yaml1 = generate_yaml("server-unique-1", 25565, 25575)
        response1 = test_client_with_temp_path.post(
            "/api/servers/server-unique-1",
            json={"yaml_content": yaml1},
            headers={"Authorization": "Bearer test-master-token"},
        )
        assert response1.status_code == 200

        # Create second server with different ports
        yaml2 = generate_yaml("server-unique-2", 25566, 25576)
        response2 = test_client_with_temp_path.post(
            "/api/servers/server-unique-2",
            json={"yaml_content": yaml2},
            headers={"Authorization": "Bearer test-master-token"},
        )

        assert response2.status_code == 200
        data = response2.json()
        assert data["message"] == "Server 'server-unique-2' created successfully"
        assert data["game_port"] == 25566
        assert data["rcon_port"] == 25576


class TestPortConflictDetection:
    """Test port conflict detection functionality."""

    def test_port_conflict_detection(self, test_client_with_temp_path):
        """Test that port conflicts are properly detected."""
        # Create first server
        yaml1 = generate_yaml("server1", 25565, 25575)
        response1 = test_client_with_temp_path.post(
            "/api/servers/server1",
            json={"yaml_content": yaml1},
            headers={"Authorization": "Bearer test-master-token"},
        )
        assert response1.status_code == 200

        # Try to create second server with same ports
        yaml2 = generate_yaml("server2", 25565, 25575)  # Same ports
        response2 = test_client_with_temp_path.post(
            "/api/servers/server2",
            json={"yaml_content": yaml2},
            headers={"Authorization": "Bearer test-master-token"},
        )

        assert response2.status_code == 409
        detail = response2.json()["detail"]
        assert "Port conflicts detected" in detail
        assert "Game port 25565 is already used by server 'server1'" in detail
        assert "RCON port 25575 is already used by server 'server1'" in detail

    def test_game_port_conflict_only(self, test_client_with_temp_path):
        """Test that only game port conflicts are detected."""
        # Create first server
        yaml1 = generate_yaml("server-base", 25565, 25575)
        response1 = test_client_with_temp_path.post(
            "/api/servers/server-base",
            json={"yaml_content": yaml1},
            headers={"Authorization": "Bearer test-master-token"},
        )
        assert response1.status_code == 200

        # Try to create second server with same game port, different RCON port
        yaml2 = generate_yaml("server-game-conflict", 25565, 25576)
        response2 = test_client_with_temp_path.post(
            "/api/servers/server-game-conflict",
            json={"yaml_content": yaml2},
            headers={"Authorization": "Bearer test-master-token"},
        )

        assert response2.status_code == 409
        detail = response2.json()["detail"]
        assert "Port conflicts detected" in detail
        assert "Game port 25565 is already used by server 'server-base'" in detail
        # Should not mention RCON port
        assert "RCON port" not in detail or "RCON port 25576" not in detail

    def test_rcon_port_conflict_only(self, test_client_with_temp_path):
        """Test that only RCON port conflicts are detected."""
        # Create first server
        yaml1 = generate_yaml("server-rcon-base", 25565, 25575)
        response1 = test_client_with_temp_path.post(
            "/api/servers/server-rcon-base",
            json={"yaml_content": yaml1},
            headers={"Authorization": "Bearer test-master-token"},
        )
        assert response1.status_code == 200

        # Try to create second server with different game port, same RCON port
        yaml2 = generate_yaml("server-rcon-conflict", 25566, 25575)
        response2 = test_client_with_temp_path.post(
            "/api/servers/server-rcon-conflict",
            json={"yaml_content": yaml2},
            headers={"Authorization": "Bearer test-master-token"},
        )

        assert response2.status_code == 409
        detail = response2.json()["detail"]
        assert "Port conflicts detected" in detail
        assert "RCON port 25575 is already used by server 'server-rcon-base'" in detail
        # Should not mention game port conflict
        assert "Game port 25566" not in detail


class TestDuplicateServerNames:
    """Test duplicate server name handling."""

    def test_duplicate_server_name_rejected(self, test_client_with_temp_path):
        """Test that duplicate server names are rejected."""
        yaml_content = generate_yaml("duplicate-name", 25567, 25577)

        # Create first server
        response1 = test_client_with_temp_path.post(
            "/api/servers/duplicate-name",
            json={"yaml_content": yaml_content},
            headers={"Authorization": "Bearer test-master-token"},
        )
        assert response1.status_code == 200

        # Try to create server with same name (even with different ports)
        yaml_different_ports = generate_yaml("duplicate-name", 25568, 25578)
        response2 = test_client_with_temp_path.post(
            "/api/servers/duplicate-name",
            json={"yaml_content": yaml_different_ports},
            headers={"Authorization": "Bearer test-master-token"},
        )

        assert response2.status_code == 409
        assert "already exists" in response2.json()["detail"]


class TestYAMLValidation:
    """Test YAML validation and error handling."""

    def test_create_server_invalid_yaml_no_version(self, test_client_with_temp_path):
        """Test creating server with invalid YAML (missing VERSION)."""
        response = test_client_with_temp_path.post(
            "/api/servers/invalid-server-no-version",
            json={"yaml_content": INVALID_YAML_NO_VERSION},
            headers={"Authorization": "Bearer test-master-token"},
        )

        assert response.status_code == 400
        assert "Could not find VERSION in environment" in response.json()["detail"]

    def test_create_server_invalid_yaml_missing_game_port(
        self, test_client_with_temp_path
    ):
        """Test creating server with invalid YAML (missing game port)."""
        response = test_client_with_temp_path.post(
            "/api/servers/invalid-server-missing-game-port",
            json={"yaml_content": INVALID_YAML_MISSING_GAME_PORT},
            headers={"Authorization": "Bearer test-master-token"},
        )

        assert response.status_code == 400
        assert "Could not find game port" in response.json()["detail"]

    def test_create_server_invalid_yaml_missing_rcon_port(
        self, test_client_with_temp_path
    ):
        """Test creating server with invalid YAML (missing RCON port)."""
        response = test_client_with_temp_path.post(
            "/api/servers/invalid-server-missing-rcon-port",
            json={"yaml_content": INVALID_YAML_MISSING_RCON_PORT},
            headers={"Authorization": "Bearer test-master-token"},
        )

        assert response.status_code == 400
        assert "Could not find rcon port" in response.json()["detail"]

    def test_create_server_invalid_yaml_syntax(self, test_client_with_temp_path):
        """Test creating server with invalid YAML syntax."""
        response = test_client_with_temp_path.post(
            "/api/servers/invalid-server-syntax",
            json={"yaml_content": INVALID_YAML_SYNTAX},
            headers={"Authorization": "Bearer test-master-token"},
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "Failed to extract ports from YAML" in detail

    def test_create_server_invalid_image(self, test_client_with_temp_path):
        """Test creating server with wrong Docker image."""
        response = test_client_with_temp_path.post(
            "/api/servers/invalid-server-wrong-image",
            json={"yaml_content": INVALID_YAML_WRONG_IMAGE},
            headers={"Authorization": "Bearer test-master-token"},
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "Service must use itzg/minecraft-server image" in detail

    def test_create_server_invalid_container_name(self, test_client_with_temp_path):
        """Test creating server with wrong container name format."""
        response = test_client_with_temp_path.post(
            "/api/servers/invalid-server-wrong-name",
            json={"yaml_content": INVALID_YAML_WRONG_CONTAINER_NAME},
            headers={"Authorization": "Bearer test-master-token"},
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "Container name must start with 'mc-'" in detail


class TestAuthenticationAuthorization:
    """Test authentication and authorization for server creation."""

    def test_create_server_unauthorized(self, test_client_with_temp_path):
        """Test creating server without authorization."""
        response = test_client_with_temp_path.post(
            "/api/servers/unauthorized-server", json={"yaml_content": VALID_YAML_BASIC}
        )

        assert response.status_code == 401

    def test_create_server_wrong_token(self, test_client_with_temp_path):
        """Test creating server with wrong authorization token."""
        response = test_client_with_temp_path.post(
            "/api/servers/wrong-token-server",
            json={"yaml_content": VALID_YAML_BASIC},
            headers={"Authorization": "Bearer wrong-token"},
        )

        assert response.status_code == 401


class TestPortExtractionUtility:
    """Test the port extraction helper function directly."""

    def test_extract_ports_valid_yaml(self):
        """Test extracting ports from valid YAML."""
        from app.routers.servers.create import extract_ports_from_yaml

        game_port, rcon_port = extract_ports_from_yaml(VALID_YAML_BASIC)
        assert game_port == 25565
        assert rcon_port == 25575

        game_port, rcon_port = extract_ports_from_yaml(VALID_YAML_DIFFERENT_PORTS)
        assert game_port == 25566
        assert rcon_port == 25576

    def test_extract_ports_invalid_yaml(self):
        """Test extracting ports from invalid YAML."""
        from app.routers.servers.create import extract_ports_from_yaml

        with pytest.raises(ValueError) as exc_info:
            extract_ports_from_yaml(INVALID_YAML_NO_VERSION)
        assert "Could not find VERSION in environment" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            extract_ports_from_yaml(INVALID_YAML_MISSING_GAME_PORT)
        assert "Could not find game port" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            extract_ports_from_yaml(INVALID_YAML_SYNTAX)
        assert "Failed to extract ports from YAML" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            extract_ports_from_yaml(INVALID_YAML_WRONG_IMAGE)
        assert "Service must use itzg/minecraft-server image" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            extract_ports_from_yaml(INVALID_YAML_WRONG_CONTAINER_NAME)
        assert "Container name must start with 'mc-'" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
