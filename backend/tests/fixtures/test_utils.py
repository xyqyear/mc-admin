from pathlib import Path

import aiofiles.os as aioos
import pytest_asyncio

from app.minecraft.utils import async_rmtree, run_shell_command

TEST_ROOT_PATH = Path("/tmp/test_temp_dir")


def create_mc_server_compose_yaml(
    server_name: str, game_port: int, rcon_port: int
) -> str:
    """Create a YAML string for a Minecraft server compose configuration"""
    return f"""services:
  mc:
    image: itzg/minecraft-server:java21-alpine
    container_name: mc-{server_name}
    environment:
      EULA: 'true'
      VERSION: 1.20.4
      INIT_MEMORY: 0M
      MAX_MEMORY: 500M
      ONLINE_MODE: 'false'
      TYPE: VANILLA
      ENABLE_RCON: 'true'
      MODE: creative
      VIEW_DISTANCE: '1'
      LEVEL_TYPE: 'minecraft:flat'
      GENERATE_STRUCTURES: 'false'
      SPAWN_NPCS: 'false'
      SPAWN_ANIMALS: 'false'
      SPAWN_MONSTERS: 'false'
      FORCE_GAMEMODE: 'true'
    ports:
    - {game_port}:25565
    - {rcon_port}:25575
    volumes:
    - ./data:/data
    stdin_open: true
    tty: true
    restart: unless-stopped
"""


@pytest_asyncio.fixture  # type: ignore
async def teardown():
    if await aioos.path.exists(TEST_ROOT_PATH):
        await async_rmtree(TEST_ROOT_PATH)
    await aioos.makedirs(TEST_ROOT_PATH)
    containers_to_remove = list[str]()
    yield containers_to_remove
    for container_name in containers_to_remove:
        await run_shell_command(f"docker rm -f {container_name}")
    await async_rmtree(TEST_ROOT_PATH)
