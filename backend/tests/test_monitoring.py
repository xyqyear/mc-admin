"""Real container identity and monitoring observations."""

import asyncio
import subprocess

import psutil
import pytest

from app.minecraft import DockerMCManager
from app.minecraft.instance import MCInstance

from .fixtures.test_utils import OwnedDockerResources

pytestmark = pytest.mark.docker


@pytest.fixture(scope="module")
async def mc_server_session(tmp_path_factory):
    resources = OwnedDockerResources(tmp_path_factory.mktemp("monitoring"))
    server_name = resources.name("monitoring")
    server = DockerMCManager(resources.root).get_instance(server_name)
    try:
        await server.create(resources.compose(server_name))
        await server.up()
        await server.wait_until_healthy()
        game_port, rcon_port = await resources.published_ports(server_name)
        assert game_port != rcon_port
        yield server
    finally:
        await resources.cleanup()


async def test_running_container_metrics_observe_real_activity(mc_server_session: MCInstance):
    server = mc_server_session
    container_id = await server.get_container_id()
    inspect = await asyncio.to_thread(
        subprocess.run, ["docker", "inspect", "--format", "{{.Id}} {{.State.Pid}}", container_id],
        capture_output=True, text=True, check=True,
    )
    actual_id, actual_pid = inspect.stdout.strip().split()
    assert container_id == actual_id
    java = psutil.Process(await server.get_pid())
    assert java.name() == "java"
    assert int(actual_pid) in {java.pid, *(parent.pid for parent in java.parents())}
    assert await server.healthy()

    memory = await server.get_memory_usage()
    assert 10 * 1024 * 1024 < memory.total_memory < 2 * 1024 * 1024 * 1024
    assert await server.get_cpu_percentage() >= 0
    disk = await server.get_disk_io()
    assert disk.devices
    assert disk.total_read_bytes >= 0 and disk.total_write_bytes >= 0

    before = await server.get_network_io()
    assert before.get_interface_by_name("lo") is not None
    await server.send_command_rcon("list")
    after = await server.get_network_io()
    assert after.total_rx_bytes > before.total_rx_bytes
    assert after.total_tx_bytes > before.total_tx_bytes


@pytest.mark.asyncio
async def test_container_not_running_error_handling(tmp_path):
    """Test error handling when container is not running"""
    docker_mc_manager = DockerMCManager(tmp_path)
    server = docker_mc_manager.get_instance("non-existent-server")

    # These should raise appropriate exceptions when container doesn't exist
    with pytest.raises(RuntimeError, match="is not created"):
        await server.get_container_id()

    with pytest.raises(RuntimeError, match="Failed to exec command"):
        await server.get_pid()

    with pytest.raises(RuntimeError, match="is not created"):
        await server.get_memory_usage()

    with pytest.raises(RuntimeError, match="Failed to exec command"):
        await server.get_cpu_percentage()

    with pytest.raises(RuntimeError, match="is not created"):
        await server.get_disk_io()

    with pytest.raises(RuntimeError, match="Failed to exec command"):
        await server.get_network_io()
