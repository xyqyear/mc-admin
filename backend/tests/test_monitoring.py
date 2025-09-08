"""
Test suite for cgroup monitoring APIs using a Minecraft server container.

This test file validates the newly added cgroup monitoring functionality:
- get_container_id()
- get_pid()
- get_memory_usage()
- get_cpu_percentage()
- get_disk_io()
- get_network_io()
"""

# pyright: reportUnusedImport=false
import asyncio
import subprocess

import aiofiles.os as aioos
import pytest
import pytest_asyncio

from app.minecraft import DockerMCManager
from app.minecraft.instance import MCInstance

from .fixtures.test_utils import (
    TEST_ROOT_PATH,
    async_rmtree,
    create_mc_server_compose_yaml,
    run_shell_command,
)


@pytest_asyncio.fixture(scope="session")  # type: ignore
async def teardown_session():
    """Session-scoped teardown fixture for cleaning up containers and directories"""
    if await aioos.path.exists(TEST_ROOT_PATH):
        await async_rmtree(TEST_ROOT_PATH)
    await aioos.makedirs(TEST_ROOT_PATH)
    containers_to_remove = list[str]()
    yield containers_to_remove
    for container_name in containers_to_remove:
        await run_shell_command(f"docker rm -f {container_name}")
    await async_rmtree(TEST_ROOT_PATH)


@pytest.fixture(scope="session")
async def mc_server_session(teardown_session: list[str]):
    """Session-scoped fixture to create and manage a Minecraft test server for monitoring"""
    server_name = "cgroup-monitoring-test"
    docker_mc_manager = DockerMCManager(TEST_ROOT_PATH)
    server = docker_mc_manager.get_instance(server_name)
    teardown_session.append(f"mc-{server_name}")

    # Create the server with Minecraft compose configuration
    await server.create(create_mc_server_compose_yaml(server_name, 39000, 39001))

    # Start the container
    await server.up()

    # Wait for it to be healthy
    await server.wait_until_healthy()

    yield server

    # Cleanup is handled by teardown_session fixture


@pytest.mark.asyncio
async def test_get_container_id_with_docker(mc_server_session: MCInstance):
    """Test that get_container_id() returns the correct Docker container ID"""
    # Get container ID from API
    api_container_id = await mc_server_session.get_container_id()

    # Get container ID from Docker command (full version)
    docker_result = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            f"name=mc-{mc_server_session.get_name()}",
            "--format",
            "{{.ID}}",
            "--no-trunc",
        ],
        capture_output=True,
        text=True,
    )
    docker_container_id = docker_result.stdout.strip()

    # They should match exactly
    assert api_container_id == docker_container_id

    # Also verify it starts with the short ID
    docker_short_result = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            f"name=mc-{mc_server_session.get_name()}",
            "--format",
            "{{.ID}}",
        ],
        capture_output=True,
        text=True,
    )
    docker_short_id = docker_short_result.stdout.strip()
    assert api_container_id.startswith(docker_short_id)


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_get_memory_usage_with_docker(mc_server_session: MCInstance):
    """Test that get_memory_usage() returns valid memory statistics"""
    memory_stats = await mc_server_session.get_memory_usage()

    # Basic validation - memory usage should be positive
    assert memory_stats.anon >= 0
    assert memory_stats.file >= 0
    assert memory_stats.kernel >= 0

    # Total memory should be reasonable for minecraft container (> 10MB, < 2GB)
    total_memory = memory_stats.total_memory
    assert total_memory > 10 * 1024 * 1024  # > 10MB
    assert total_memory < 2 * 1024 * 1024 * 1024  # < 2GB

    # Active memory should be sum of active_anon + active_file
    assert (
        memory_stats.active_memory
        == memory_stats.active_anon + memory_stats.active_file
    )


@pytest.mark.asyncio
async def test_get_cpu_percentage_with_docker(mc_server_session: MCInstance):
    """Test that get_cpu_percentage() works correctly"""
    cpu_percent = await mc_server_session.get_cpu_percentage()

    # Second call should return a valid percentage (>= 0, <= 100)
    assert cpu_percent >= 0.0
    assert cpu_percent <= 100.0


@pytest.mark.asyncio
async def test_get_disk_io_with_docker(mc_server_session: MCInstance):
    """Test that get_disk_io() returns valid disk I/O statistics"""
    disk_io = await mc_server_session.get_disk_io()

    # Should have at least one device
    assert len(disk_io.devices) > 0

    # Total values should be non-negative
    assert disk_io.total_read_bytes >= 0
    assert disk_io.total_write_bytes >= 0
    assert disk_io.total_bytes >= 0

    # Total bytes should equal sum of read + write + discard
    expected_total = sum(
        device.rbytes + device.wbytes + device.dbytes for device in disk_io.devices
    )
    assert disk_io.total_bytes == expected_total

    # Each device should have valid properties
    for device in disk_io.devices:
        assert device.major >= 0
        assert device.minor >= 0
        assert device.rbytes >= 0
        assert device.wbytes >= 0
        assert ":" in device.device_id  # Should be in "major:minor" format


@pytest.mark.asyncio
async def test_get_network_io_with_docker(mc_server_session: MCInstance):
    """Test that get_network_io() returns valid network I/O statistics"""
    network_io = await mc_server_session.get_network_io()

    # Should have at least loopback interface
    assert len(network_io.interfaces) > 0

    # Should have loopback (lo) interface
    lo_interface = network_io.get_interface_by_name("lo")
    assert lo_interface is not None

    # Total values should be non-negative
    assert network_io.total_rx_bytes >= 0
    assert network_io.total_tx_bytes >= 0
    assert network_io.total_rx_packets >= 0
    assert network_io.total_tx_packets >= 0

    # Each interface should have valid properties
    for interface in network_io.interfaces:
        assert interface.rx_bytes >= 0
        assert interface.tx_bytes >= 0
        assert interface.rx_packets >= 0
        assert interface.tx_packets >= 0
        assert len(interface.name) > 0


@pytest.mark.asyncio
async def test_all_apis_integration_with_docker(mc_server_session: MCInstance):
    """Integration test that verifies all monitoring APIs work together"""
    # Test that we can get all metrics without errors
    container_id = await mc_server_session.get_container_id()
    pid = await mc_server_session.get_pid()
    memory_stats = await mc_server_session.get_memory_usage()

    # Establish CPU baseline
    await mc_server_session.get_cpu_percentage()
    await asyncio.sleep(2)
    cpu_percentage = await mc_server_session.get_cpu_percentage()

    disk_io = await mc_server_session.get_disk_io()
    network_io = await mc_server_session.get_network_io()

    # Verify all data is consistent
    assert len(container_id) == 64  # Full Docker container ID length
    assert pid > 0
    assert memory_stats.total_memory > 0
    assert 0 <= cpu_percentage <= 100
    assert len(disk_io.devices) > 0
    assert len(network_io.interfaces) > 0

    # Test that the container is actually running and healthy
    assert await mc_server_session.running()
    assert await mc_server_session.healthy()


@pytest.mark.asyncio
async def test_container_not_running_error_handling():
    """Test error handling when container is not running"""
    docker_mc_manager = DockerMCManager(TEST_ROOT_PATH)
    server = docker_mc_manager.get_instance("non-existent-server")

    # These should raise appropriate exceptions when container doesn't exist
    with pytest.raises(Exception):  # Could be various types depending on implementation
        await server.get_container_id()

    with pytest.raises(Exception):
        await server.get_pid()

    with pytest.raises(Exception):
        await server.get_memory_usage()

    with pytest.raises(Exception):
        await server.get_cpu_percentage()

    with pytest.raises(Exception):
        await server.get_disk_io()

    with pytest.raises(Exception):
        await server.get_network_io()
