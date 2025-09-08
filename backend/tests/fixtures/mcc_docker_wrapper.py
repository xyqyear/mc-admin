import asyncio
from pathlib import Path

import aiofiles
import aiofiles.os as aioos

from app.minecraft.docker.manager import ComposeManager

docker_compose_content_template = """
services:
  mcc:
    image: ghcr.io/xyqyear/minecraft-console-client
    container_name: mcc-{username}
    command: ["{username}", "-", "{server}"]
    network_mode: host
    stdin_open: true
    tty: true
"""


class MCCDockerWrapper:
    def __init__(self, path: str | Path, username: str, server: str):
        self.path = Path(path)
        self.docker_compose_path = self.path / "docker-compose.yml"
        self.docker_compose_content = docker_compose_content_template.format(
            username=username, server=server
        )
        self.compose_manager = ComposeManager(self.path)

    async def create(self):
        await aioos.makedirs(self.path, exist_ok=True)
        async with aiofiles.open(self.docker_compose_path, "w") as f:
            await f.write(self.docker_compose_content)

    async def up(self):
        await self.compose_manager.up_detached()

    async def down(self):
        await self.compose_manager.down()

    async def chat(self, text: str):
        await self.compose_manager.send_to_stdin("mcc", f"/send {text}")

    async def is_connected(self) -> bool:
        logs = await self.compose_manager.logs()
        return "joined" in logs

    async def wait_until_connected(self, timeout: float = 10):
        """
        timeout: seconds
        """
        while timeout > 0:
            logs = await self.compose_manager.logs()
            if "joined" in logs:
                return
            if "failed" in logs:
                raise RuntimeError("Failed to connect to the server")
            await asyncio.sleep(0.5)
            timeout -= 0.5
        raise TimeoutError("Timed out while waiting for the connection")
