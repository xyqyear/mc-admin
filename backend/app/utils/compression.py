"""7z compression of Minecraft server files."""

import re
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Optional

from aiofiles import os as aioos

from app.minecraft.instance import MCInstance

from ..background_tasks.types import TaskProgress
from ..config import settings
from . import async_fs
from .exec import exec_command_stream


def _sanitize_filename_part(part: str) -> str:
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

    sanitized = sanitized.strip(". ")

    if not sanitized:
        sanitized = "unknown"

    return sanitized


def _generate_archive_filename(
    server_name: str, relative_path: Optional[str] = None
) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    safe_server_name = _sanitize_filename_part(server_name)

    filename_parts = [safe_server_name]

    if relative_path and relative_path != "/":
        path_parts = [part for part in relative_path.strip("/").split("/") if part]
        if path_parts:
            safe_path = "_".join(_sanitize_filename_part(part) for part in path_parts)
            filename_parts.append(safe_path)

    filename_parts.append(timestamp)

    filename = "_".join(filename_parts) + ".7z"

    return filename


async def create_server_archive_stream(
    instance: MCInstance, relative_path: Optional[str] = None
) -> AsyncGenerator[TaskProgress, None]:
    """Create a 7z archive of an instance's files, yielding ``TaskProgress`` updates."""
    archive_base_path = await async_fs.resolve(settings.archive_path)
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
        raise RuntimeError(f"Source path does not exist: {source_path}")

    source_parent = source_path.parent
    source_name = source_path.name

    yield TaskProgress(progress=0, message="Starting compression...")

    # 7z rewrites the progress line with \r and \x08 between updates.
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
