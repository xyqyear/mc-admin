# pyright: reportUnusedImport=false
import pytest

from app.minecraft import DiskSpaceInfo, DockerMCManager, MCServerInfo, MCServerStatus
from app.minecraft.compose import ServerType

from .fixtures.test_utils import (
    TEST_ROOT_PATH,
    create_mc_server_compose_yaml,
    teardown,  # noqa: F401 -- for pytest fixture
)


@pytest.mark.asyncio
async def test_minecraft_instance(teardown: list[str]):
    docker_mc_manager = DockerMCManager(TEST_ROOT_PATH)
    server1 = docker_mc_manager.get_instance("testserver1")
    teardown.append("mc-testserver1")

    await server1.create(create_mc_server_compose_yaml("testserver1", 34544, 34544 + 1))
    server_info = await server1.get_server_info()
    expected_info = MCServerInfo(
        name="testserver1",
        path=server1.get_project_path(),
        java_version=21,
        max_memory_bytes=524288000,  # 500M in bytes = 500 * 1024 * 1024
        server_type=ServerType.VANILLA,
        game_version="1.20.4",
        game_port=34544,
        rcon_port=34545,
    )
    assert server_info == expected_info
    mc_compose = await server1.get_compose_obj()

    assert mc_compose.get_server_name() == "testserver1"
    assert mc_compose.get_game_version() == "1.20.4"
    assert mc_compose.get_game_port() == 34544
    assert mc_compose.get_rcon_port() == 34545


@pytest.mark.asyncio
async def test_server_status_lifecycle(teardown: list[str]):
    """Test the complete lifecycle of server status changes"""
    docker_mc_manager = DockerMCManager(TEST_ROOT_PATH)
    server = docker_mc_manager.get_instance("status-test-server")
    teardown.append("mc-status-test-server")

    # Test REMOVED status - server doesn't exist
    print("Testing REMOVED status")
    assert await server.get_status() == MCServerStatus.REMOVED
    assert not await server.exists()
    assert not await server.created()
    assert not await server.running()
    assert not await server.healthy()

    # Create server -> EXISTS status
    print("Testing EXISTS status")
    await server.create(
        create_mc_server_compose_yaml("status-test-server", 34600, 34601)
    )
    assert await server.get_status() == MCServerStatus.EXISTS
    assert await server.exists()
    assert not await server.created()
    assert not await server.running()
    assert not await server.healthy()

    # Start container -> CREATED, then RUNNING status
    await server.up()

    # Should be STARTING
    print("Testing STARTING status")
    assert await server.get_status() == MCServerStatus.STARTING
    assert await server.exists()
    assert await server.created()
    assert await server.starting()
    assert await server.running()

    # Wait for server to become healthy
    await server.wait_until_healthy()

    # Should now be HEALTHY
    print("Testing HEALTHY status")
    assert await server.get_status() == MCServerStatus.HEALTHY
    assert await server.exists()
    assert await server.created()
    assert await server.running()
    assert await server.healthy()

    await server.restart()
    print("Testing STARTING status after restart")
    assert await server.get_status() == MCServerStatus.STARTING
    assert await server.exists()
    assert await server.created()
    assert await server.starting()
    assert await server.running()
    assert not await server.healthy()

    # Stop server -> back to CREATED
    await server.stop()
    print("Testing CREATED status after stop")
    assert await server.get_status() == MCServerStatus.CREATED
    assert await server.exists()
    assert await server.created()
    assert not await server.running()
    assert not await server.healthy()

    # Remove container -> back to EXISTS
    await server.down()
    print("Testing EXISTS status after down")
    assert await server.get_status() == MCServerStatus.EXISTS
    assert await server.exists()
    assert not await server.created()
    assert not await server.running()
    assert not await server.healthy()

    # Remove server completely -> REMOVED
    await server.remove()
    print("Testing REMOVED status after remove")
    assert await server.get_status() == MCServerStatus.REMOVED
    assert not await server.exists()
    assert not await server.created()
    assert not await server.running()
    assert not await server.healthy()


@pytest.mark.asyncio
async def test_disk_space_info_dataclass():
    """Test DiskSpaceInfo dataclass functionality"""
    # Test normal case
    disk_info = DiskSpaceInfo(
        used_bytes=1024 * 1024 * 1024,  # 1GB used
        total_bytes=10 * 1024 * 1024 * 1024,  # 10GB total
        available_bytes=9 * 1024 * 1024 * 1024,  # 9GB available
    )

    assert disk_info.used_bytes == 1024 * 1024 * 1024
    assert disk_info.total_bytes == 10 * 1024 * 1024 * 1024
    assert disk_info.available_bytes == 9 * 1024 * 1024 * 1024
    assert disk_info.usage_percentage == 10.0  # 1GB / 10GB = 10%

    # Test edge case with zero total
    disk_info_zero = DiskSpaceInfo(
        used_bytes=0,
        total_bytes=0,
        available_bytes=0,
    )
    assert disk_info_zero.usage_percentage == 0.0

    # Test 100% usage case
    disk_info_full = DiskSpaceInfo(
        used_bytes=1000,
        total_bytes=1000,
        available_bytes=0,
    )
    assert disk_info_full.usage_percentage == 100.0


@pytest.mark.asyncio
async def test_get_disk_space_info(teardown: list[str]):
    """Test get_disk_space_info method"""
    docker_mc_manager = DockerMCManager(TEST_ROOT_PATH)
    server = docker_mc_manager.get_instance("disk-space-test")
    teardown.append("mc-disk-space-test")

    # Test error when data directory doesn't exist
    with pytest.raises(RuntimeError, match="Data directory does not exist"):
        await server.get_disk_space_info()

    # Create server to set up data directory
    await server.create(create_mc_server_compose_yaml("disk-space-test", 34650, 34651))

    # Test successful disk space info retrieval
    disk_info = await server.get_disk_space_info()
    assert isinstance(disk_info, DiskSpaceInfo)
    assert disk_info.used_bytes >= 0
    assert disk_info.total_bytes > 0
    assert disk_info.available_bytes >= 0
    assert disk_info.total_bytes >= disk_info.used_bytes

    # Test that usage percentage is calculated correctly
    expected_percentage = (disk_info.used_bytes / disk_info.total_bytes) * 100
    assert abs(disk_info.usage_percentage - expected_percentage) < 0.01


@pytest.mark.asyncio
async def test_get_disk_usage_backward_compatibility(teardown: list[str]):
    """Test that get_disk_usage maintains backward compatibility"""
    docker_mc_manager = DockerMCManager(TEST_ROOT_PATH)
    server = docker_mc_manager.get_instance("disk-usage-compat-test")
    teardown.append("mc-disk-usage-compat-test")

    # Create server to set up data directory
    await server.create(
        create_mc_server_compose_yaml("disk-usage-compat-test", 34652, 34653)
    )

    # Test that get_disk_usage returns the same as get_disk_space_info.used_bytes
    disk_usage = await server.get_disk_usage()
    disk_space_info = await server.get_disk_space_info()

    assert disk_usage == disk_space_info.used_bytes
    assert isinstance(disk_usage, int)


@pytest.mark.asyncio
async def test_server_running_info_with_disk_space(teardown: list[str]):
    """Test that MCServerRunningInfo includes complete disk space information"""
    docker_mc_manager = DockerMCManager(TEST_ROOT_PATH)
    server = docker_mc_manager.get_instance("running-info-disk-test")
    teardown.append("mc-running-info-disk-test")

    # Create and start server
    await server.create(
        create_mc_server_compose_yaml("running-info-disk-test", 34654, 34655)
    )
    await server.up()

    # Wait for server to be running
    await server.wait_until_healthy()

    # Get server running info
    running_info = await server.get_server_running_info()

    # Test that all disk space fields are present and valid
    assert running_info.disk_usage_bytes >= 0
    assert running_info.disk_total_bytes > 0
    assert running_info.disk_available_bytes >= 0

    # Test total = used + available (approximately, allowing for filesystem overhead)
    total_accounted = running_info.disk_usage_bytes + running_info.disk_available_bytes
    # Allow some tolerance for filesystem overhead
    assert (
        abs(running_info.disk_total_bytes - total_accounted)
        / running_info.disk_total_bytes
        < 0.1
    )

    # Test disk usage percentage calculation
    expected_percentage = (
        running_info.disk_usage_bytes / running_info.disk_total_bytes
    ) * 100
    assert abs(running_info.disk_usage_percentage - expected_percentage) < 0.01

    # Test that other fields are still present
    assert running_info.cpu_percentage >= 0
    assert running_info.memory_usage_bytes >= 0
    assert running_info.disk_read_bytes >= 0
    assert running_info.disk_write_bytes >= 0
    assert running_info.network_receive_bytes >= 0
    assert running_info.network_send_bytes >= 0
