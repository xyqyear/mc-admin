"""
Command execution utilities for running system commands and shell operations.
"""

import asyncio
import os
import shutil
from pathlib import Path

from asyncer import asyncify


@asyncify
def async_rmtree(path: Path):
    """Asynchronously remove a directory tree."""
    shutil.rmtree(path)


async def run_shell_command(command: str, catch_output: bool = True) -> str:
    """
    Run shell command asynchronously.

    Args:
        command: Shell command to execute
        catch_output: Whether to capture output (need to use catch_output=False for socat)

    Returns:
        Command output as string

    Raises:
        RuntimeError: If command fails
    """
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE if catch_output else None,
        stderr=asyncio.subprocess.PIPE if catch_output else None,
    )

    stdout, stderr = await process.communicate()
    if stdout is None:  # type: ignore
        stdout = b""
    if stderr is None:  # type: ignore
        stderr = b""

    if process.returncode != 0:
        raise RuntimeError(f"Failed to run shell command: {command}\n{stderr.decode()}")
    return stdout.decode()


async def exec_command(
    command: str,
    *args: str,
    uid: int | None = None,
    gid: int | None = None,
    env: dict[str, str] = dict(),
    cwd: str | None = None,
) -> str:
    """
    Execute command with arguments asynchronously.

    Args:
        command: Command to execute
        *args: Command arguments
        uid: User ID to run command as
        gid: Group ID to run command as
        env: Environment variables
        cwd: Working directory

    Returns:
        Command output as string

    Raises:
        RuntimeError: If command fails
    """

    def demote():
        if uid is not None and gid is not None:
            os.setuid(uid)
            os.setgid(gid)

    process = await asyncio.create_subprocess_exec(
        command,
        *args,
        preexec_fn=demote,
        env=env,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()
    if stdout is None:  # type: ignore
        stdout = b""
    if stderr is None:  # type: ignore
        stderr = b""

    if process.returncode != 0:
        raise RuntimeError(
            f"Failed to exec command: {command}\n{stderr.decode()}\n{stdout.decode()}"
        )
    return stdout.decode()
