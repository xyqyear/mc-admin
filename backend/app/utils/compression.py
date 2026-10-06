"""7z compression of Minecraft server files."""

import re
from collections.abc import AsyncGenerator, Sequence
from contextlib import aclosing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from aiofiles import os as aioos

from app.minecraft.instance import MCInstance

from ..background_tasks.types import TaskProgress
from ..config import get_settings
from ..errors import PublicOperationError
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


def generate_archive_filename(
    server_name: str, relative_path: str | None = None
) -> str:
    timestamp = datetime.now(UTC).astimezone().replace(tzinfo=None).strftime("%Y%m%d_%H%M%S")

    safe_server_name = _sanitize_filename_part(server_name)

    filename_parts = [safe_server_name]

    if relative_path and relative_path != "/":
        path_parts = [part for part in relative_path.strip("/").split("/") if part]
        if path_parts:
            safe_path = "_".join(_sanitize_filename_part(part) for part in path_parts)
            filename_parts.append(safe_path)

    filename_parts.append(timestamp)
    filename_parts.append(uuid4().hex)

    filename = "_".join(filename_parts) + ".7z"

    return filename


async def create_server_archive_stream(
    instance: MCInstance, relative_path: str | None = None, *, output_path: Path | None = None,
    relative_paths: Sequence[str] | None = None,
) -> AsyncGenerator[TaskProgress]:
    """Create a 7z archive of an instance's files, yielding ``TaskProgress`` updates."""
    settings = get_settings()
    archive_base_path = await async_fs.resolve(settings.archive_path)
    await aioos.makedirs(archive_base_path, exist_ok=True)

    archive_filename = output_path.name if output_path is not None else generate_archive_filename(instance.get_name(), relative_path)
    archive_path = output_path if output_path is not None else archive_base_path / archive_filename

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
        raise PublicOperationError("压缩源路径不存在，请刷新文件列表后重试")

    if relative_paths is not None:
        source_parent = instance.get_data_path()
        source_names = [path or "." for path in relative_paths]
        for path in relative_paths:
            if not await aioos.path.exists(source_parent / path):
                raise PublicOperationError("压缩源路径不存在，请刷新文件列表后重试")
    else:
        source_parent = source_path.parent
        source_names = ["./" + source_path.name]

    yield TaskProgress(progress=0, message="正在准备压缩")

    # 7z rewrites the progress line with \r and \x08 between updates.
    progress_delimiters = {ord("\r"), ord("\n"), ord("\x08")}

    try:
        batches: list[list[str]] = [[]]
        argument_bytes = 0
        for name in source_names:
            size = len(name.encode()) + 4
            if batches[-1] and argument_bytes + size > 32_768:
                batches.append([])
                argument_bytes = 0
            batches[-1].append(name)
            argument_bytes += size
        for index, names in enumerate(batches):
            # Include switches preserve literal @ filenames without listfile parsing.
            include = ["-i!" + name for name in names] if relative_paths is not None else []
            async with aclosing(exec_command_stream(
                "7z", "a", "-t7z", "-bsp1", "-spd", "-snl",
                *(["-spf"] if relative_paths is not None and source_names != ["."] else []),
                *include, str(archive_path), "--",
                *(names if relative_paths is None else []),
                cwd=str(source_parent), delimiters=progress_delimiters,
            )) as stream:
                async for segment in stream:
                    match = re.search(r"^\s*(\d+)%", segment)
                    if match:
                        progress = (index * 100 + int(match.group(1))) / len(batches)
                        yield TaskProgress(progress=progress, message=f"正在压缩：{progress:.0f}%")

        archive_size = (await aioos.stat(archive_path)).st_size

        yield TaskProgress(
            progress=100,
            message="压缩完成",
            result={"filename": archive_filename, "size": archive_size},
        )
    except BaseException:
        if output_path is None and await aioos.path.exists(archive_path):
            try:
                await aioos.remove(archive_path)
            except OSError:
                pass
        raise
