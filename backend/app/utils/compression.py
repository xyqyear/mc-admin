"""
Utility for compressing Minecraft server files and directories.
"""

import re
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Optional

from aiofiles import os as aioos
from fastapi import HTTPException

from app.minecraft.instance import MCInstance

from ..background_tasks.types import TaskProgress
from ..config import settings
from .exec import exec_command_stream


def _sanitize_filename_part(part: str) -> str:
    """
    Sanitize a filename part by replacing filesystem-sensitive characters.

    Args:
        part: The string to sanitize

    Returns:
        Sanitized string safe for filesystem use
    """
    # Replace filesystem-sensitive characters
    replacements = {
        "/": "_",
        "\\": "_",
        ":": "_",
        "*": "_",
        "?": "_",
        '"': "_",
        "<": "_",
        ">": "_",
        "|": "_",
        " ": "_",
    }

    sanitized = part
    for char, replacement in replacements.items():
        sanitized = sanitized.replace(char, replacement)

    # Remove leading/trailing dots and spaces
    sanitized = sanitized.strip(". ")

    # Ensure it's not empty
    if not sanitized:
        sanitized = "unknown"

    return sanitized


def _generate_archive_filename(
    server_name: str, relative_path: Optional[str] = None
) -> str:
    """
    Generate a filename for the compressed archive.

    Args:
        server_name: The name of the server
        relative_path: Optional relative path within the server

    Returns:
        Generated filename with timestamp and sanitized components
    """
    # Get current timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Sanitize server name
    safe_server_name = _sanitize_filename_part(server_name)

    # Build filename components
    filename_parts = [safe_server_name]

    if relative_path and relative_path != "/":
        # Sanitize and add path component
        # Remove leading/trailing slashes and split into parts
        path_parts = [part for part in relative_path.strip("/").split("/") if part]
        if path_parts:
            safe_path = "_".join(_sanitize_filename_part(part) for part in path_parts)
            filename_parts.append(safe_path)

    # Add timestamp
    filename_parts.append(timestamp)

    # Join with underscores and add .7z extension
    filename = "_".join(filename_parts) + ".7z"

    return filename


async def create_server_archive_stream(
    instance: MCInstance, relative_path: Optional[str] = None
) -> AsyncGenerator[TaskProgress, None]:
    """
    Create a compressed archive of server files, yielding progress updates.

    Args:
        instance: MCInstance for the server
        relative_path: Optional relative path within the server to compress

    Yields:
        TaskProgress with progress percentage and messages

    Raises:
        HTTPException: If archive creation fails
    """
    archive_base_path = settings.archive_path.resolve()
    await aioos.makedirs(archive_base_path, exist_ok=True)

    archive_filename = _generate_archive_filename(instance.get_name(), relative_path)
    archive_path = archive_base_path / archive_filename

    if relative_path is None:
        source_path = instance.get_project_path()
    else:
        data_dir = instance.get_data_path()
        clean_relative_path = relative_path.lstrip("/")
        if clean_relative_path == "":
            source_path = data_dir
        else:
            source_path = data_dir / clean_relative_path

    if not await aioos.path.exists(source_path):
        raise HTTPException(
            status_code=404, detail=f"Source path does not exist: {source_path}"
        )

    source_parent = source_path.parent
    source_name = source_path.name

    yield TaskProgress(progress=0, message="Starting compression...")

    # Use custom delimiters for 7z progress output
    # 7z uses \r and \x08 (backspace) to update progress on the same line
    progress_delimiters = {ord("\r"), ord("\n"), ord("\x08")}

    try:
        async for segment in exec_command_stream(
            "7z",
            "a",
            "-t7z",
            "-bsp1",
            str(archive_path),
            source_name,
            cwd=str(source_parent),
            delimiters=progress_delimiters,
        ):
            match = re.search(r"^\s*(\d+)%", segment)
            if match:
                progress = int(match.group(1))
                yield TaskProgress(
                    progress=progress, message=f"Compressing: {progress}%"
                )

        archive_size = (await aioos.stat(archive_path)).st_size

        yield TaskProgress(
            progress=100,
            message="Compression complete",
            result={"filename": archive_filename, "size": archive_size},
        )
    except Exception:
        if await aioos.path.exists(archive_path):
            try:
                await aioos.remove(archive_path)
            except OSError:
                pass
        raise
