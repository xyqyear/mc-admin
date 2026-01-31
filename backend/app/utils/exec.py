"""
Command execution utilities for running system commands and shell operations.
"""

import asyncio
import os
import shutil
from collections.abc import AsyncGenerator
from pathlib import Path

from asyncer import asyncify


@asyncify
def async_rmtree(path: Path):
    """Asynchronously remove a directory tree."""
    shutil.rmtree(path)


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


async def exec_command_stream(
    command: str,
    *args: str,
    cwd: str | None = None,
    delimiters: set[int] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Execute command and yield stdout segments as they arrive.

    Args:
        command: Command to execute
        *args: Command arguments
        cwd: Working directory
        delimiters: Set of byte values to use as segment delimiters.
            If None, uses line-based reading (splits on newline).
            For 7z progress output, use {ord('\\r'), ord('\\n'), ord('\\x08')}.

    Yields:
        Segments from stdout as they arrive (split by delimiters)

    Raises:
        RuntimeError: If command fails
    """
    process = await asyncio.create_subprocess_exec(
        command,
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    if process.stdout is None:
        raise RuntimeError("Failed to capture stdout")

    if delimiters is None:
        # Default line-based reading
        async for line in process.stdout:
            yield line.decode()
    else:
        # Custom delimiter-based reading for real-time progress
        buffer = b""
        while True:
            byte = await process.stdout.read(1)
            if not byte:
                break

            if byte[0] in delimiters:
                if buffer:
                    yield buffer.decode(errors="replace")
                    buffer = b""
            else:
                buffer += byte

        # Yield remaining buffer
        if buffer:
            yield buffer.decode(errors="replace")

    await process.wait()
    if process.returncode != 0:
        stderr_content = b""
        if process.stderr:
            stderr_content = await process.stderr.read()
        raise RuntimeError(f"Command failed: {stderr_content.decode()}")
