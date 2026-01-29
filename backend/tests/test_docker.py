# pyright: reportUnusedImport=false
import asyncio
import random
import re
from dataclasses import dataclass

import aiofiles.os as aioos
import docker
import pytest

from app.minecraft import (
    DockerMCManager,
    MCServerInfo,
)
from app.minecraft.compose import ServerType
from app.minecraft.docker.manager import DockerManager

from .fixtures.mc_client import MinecraftClient
from .fixtures.test_utils import (
    TEST_ROOT_PATH,
    create_mc_server_compose_yaml,
    teardown,  # noqa: F401
)

# Pattern for parsing player messages from Minecraft logs
PLAYER_MESSAGE_PATTERN = re.compile(
    r"\]: (?:\[Not Secure\] )?<(?P<player>.*?)> (?P<message>.*)"
)


@dataclass
class PlayerMessage:
    """Player message parsed from logs."""

    player: str
    message: str


async def get_player_messages_from_docker_logs(
    instance, tail: int = 1000
) -> list[PlayerMessage]:
    """
    Get player messages from Docker container logs using docker-py.

    Args:
        instance: MCInstance to get logs from
        tail: Number of log lines to fetch

    Returns:
        List of PlayerMessage objects
    """
    container_id = await instance.get_container_id()

    # Use docker-py to fetch logs
    client = docker.APIClient(base_url="unix://var/run/docker.sock")
    try:
        logs_bytes = client.logs(
            container_id,
            stdout=True,
            stderr=True,
            tail=tail,
        )
        logs_content = logs_bytes.decode("utf-8", errors="replace")
    finally:
        client.close()

    # Parse player messages from logs
    messages = []
    for match in PLAYER_MESSAGE_PATTERN.finditer(logs_content):
        messages.append(
            PlayerMessage(
                player=match.group("player"),
                message=match.group("message").strip(),
            )
        )

    return messages


@pytest.mark.asyncio
async def test_integration_with_docker(teardown: list[str]):  # noqa: F811
    # setting up
    docker_mc_manager = DockerMCManager(TEST_ROOT_PATH)

    server1 = docker_mc_manager.get_instance("testserver1")
    server2 = docker_mc_manager.get_instance("testserver2")
    client1 = MinecraftClient("client1")
    client2 = MinecraftClient("client2")
    teardown.append("mc-testserver1")
    teardown.append("mc-testserver2")

    assert not await server1.exists()
    assert not await server2.exists()

    assert set(await docker_mc_manager.get_all_server_names()) == set()

    server1_compose_yaml = create_mc_server_compose_yaml(
        "testserver1", 34544, 34544 + 1
    )
    server2_compose_yaml = create_mc_server_compose_yaml(
        "testserver2", 34554, 34554 + 1
    )
    server1_create_coroutine = server1.create(server1_compose_yaml)
    server2_create_coroutine = server2.create(server2_compose_yaml)
    await aioos.makedirs(TEST_ROOT_PATH / "irrelevant_dir", exist_ok=True)
    await asyncio.gather(server1_create_coroutine, server2_create_coroutine)
    assert set(await docker_mc_manager.get_all_server_names()) == set(
        ["testserver1", "testserver2"]
    )
    assert set(await docker_mc_manager.get_all_server_compose_paths()) == set(
        [
            TEST_ROOT_PATH / "testserver1/docker-compose.yml",
            TEST_ROOT_PATH / "testserver2/docker-compose.yml",
        ]
    )
    assert set(await docker_mc_manager.get_all_server_info()) == set(
        [
            MCServerInfo(
                name="testserver1",
                path=server1.get_project_path(),
                java_version=25,
                max_memory_bytes=524288000,  # 500M in bytes
                server_type=ServerType.VANILLA,
                game_version="1.21.11",
                game_port=34544,
                rcon_port=34544 + 1,
            ),
            MCServerInfo(
                name="testserver2",
                path=server2.get_project_path(),
                java_version=25,
                max_memory_bytes=524288000,  # 500M in bytes
                server_type=ServerType.VANILLA,
                game_version="1.21.11",
                game_port=34554,
                rcon_port=34554 + 1,
            ),
        ]
    )
    assert set(await docker_mc_manager.get_running_server_names()) == set()

    print("servers created")

    await server1.up()
    await server2.up()
    print("servers up")

    wait_server1_coroutine = server1.wait_until_healthy()
    wait_server2_coroutine = server2.wait_until_healthy()
    await asyncio.gather(wait_server1_coroutine, wait_server2_coroutine)

    assert set(await docker_mc_manager.get_running_server_names()) == set(
        ["testserver1", "testserver2"]
    )

    print("servers healthy")

    await server2.down()

    assert await server1.list_players() == []

    await client1.connect("localhost", 34544)
    await asyncio.sleep(1)

    print("client1 connected")

    assert await server1.list_players() == ["client1"]

    await client2.connect("localhost", 34544)
    await asyncio.sleep(1)

    print("client2 connected")

    assert set(await server1.list_players()) == set(["client1", "client2"])

    random_text1 = str(random.random())
    random_text2 = str(random.random())
    random_text3 = str(random.random())

    await client1.send_chat(random_text1)
    await asyncio.sleep(1)

    print("client1 chat")

    messages = await get_player_messages_from_docker_logs(server1)
    assert messages == [PlayerMessage("client1", random_text1)]

    print("server1 verify chat")

    await client1.send_chat(random_text2)
    await asyncio.sleep(1)

    assert (await get_player_messages_from_docker_logs(server1)) == [
        PlayerMessage("client1", random_text1),
        PlayerMessage("client1", random_text2),
    ]

    print("server1 verify chat 2")

    await client2.send_chat(random_text3)
    await asyncio.sleep(1)

    assert (await get_player_messages_from_docker_logs(server1)) == [
        PlayerMessage("client1", random_text1),
        PlayerMessage("client1", random_text2),
        PlayerMessage("client2", random_text3),
    ]

    print("server1 verify chat 3")

    await client1.disconnect()
    await client2.disconnect()

    assert await server1.list_players() == []

    # Test update_compose_file functionality while server is running
    print("Starting update_compose_file tests")

    original_compose = await server1.get_compose_file()
    print("Read original compose file")
    updated_compose = original_compose.replace("MODE: creative", "MODE: survival")

    # Try to update while server is running - should fail with RuntimeError
    with pytest.raises(RuntimeError, match="while it is created"):
        await server1.update_compose_file(updated_compose)
    print("✅ Correctly caught RuntimeError when trying to update running server")

    # Bring server down for update
    await server1.down()
    print("Brought server down for update")

    # Now update should succeed
    await server1.update_compose_file(updated_compose)
    print("Successfully updated compose file")

    # Bring the server up again to verify the update worked
    await server1.up()
    await server1.wait_until_healthy()
    print("Server is running again with updated config")

    # Verify the environment variable via DockerManager
    docker_env_output = await DockerManager.run_sub_command(
        "inspect",
        "mc-testserver1",
        "--format",
        "{{range .Config.Env}}{{println .}}{{end}}",
    )
    assert "MODE=survival" in docker_env_output
    print("✅ Verified compose file change via docker inspect")

    print("✅ update_compose_file tests completed successfully")

    # Final cleanup
    await server1.down()
    print("server1 down")
