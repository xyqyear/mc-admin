from pathlib import Path

from ...utils.exec import exec_command


class ComposeManager:
    def __init__(self, project_path: str | Path) -> None:
        self.project_path = Path(project_path)

    async def run_compose_command(self, *args: str) -> str:
        return await exec_command(
            "docker",
            "compose",
            "--project-directory",
            str(self.project_path),
            *args,
        )

    async def up_detached(self):
        await self.run_compose_command("up", "-d")

    async def down(self):
        await self.run_compose_command("down")

    async def stop(self):
        await self.run_compose_command("stop")

    async def start(self):
        await self.run_compose_command("start")

    async def restart(self):
        await self.run_compose_command("restart")
