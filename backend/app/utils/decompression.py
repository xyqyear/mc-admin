"""
Utility for decompressing and extracting Minecraft server files.
"""

import re
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Literal

from aiofiles import os as aioos
from pydantic import BaseModel

from ..background_tasks.types import TaskProgress
from ..config import settings
from ..files.utils import get_uid_gid
from .exec import async_rmtree, exec_command, exec_command_stream


class DecompressionStepResult(BaseModel):
    """Result for each decompression step."""

    step: Literal[
        "archiveFileCheck",
        "serverPropertiesCheck",
        "decompress",
        "chown",
        "findPath",
        "mv",
        "remove",
    ]
    success: bool
    message: str


# Progress mapping for extraction steps
STEP_PROGRESS = {
    "archiveFileCheck": (0, 5),  # 0-5%
    "serverPropertiesCheck": (5, 10),  # 5-10%
    "decompress": (10, 80),  # 10-80% (bulk of time)
    "chown": (80, 85),  # 80-85%
    "findPath": (85, 90),  # 85-90%
    "mv": (90, 95),  # 90-95%
    "remove": (95, 100),  # 95-100%
}

STEP_NAMES = {
    "archiveFileCheck": "检查压缩包",
    "serverPropertiesCheck": "验证server.properties",
    "decompress": "解压文件",
    "chown": "设置权限",
    "findPath": "查找服务器目录",
    "mv": "移动文件",
    "remove": "清理临时文件",
}


async def extract_archive_stream(
    archive_path: str,
    output_dir: str,
) -> AsyncGenerator[int, None]:
    """
    Extract archive with real-time progress updates.

    Args:
        archive_path: Path to the archive file
        output_dir: Directory to extract to

    Yields:
        int: Progress percentage (0-100)

    Raises:
        RuntimeError: If extraction fails
    """
    # 7z uses \r and \x08 to update progress on same line
    progress_delimiters = {ord("\r"), ord("\n"), ord("\x08")}

    async for segment in exec_command_stream(
        "7z",
        "x",
        archive_path,
        f"-o{output_dir}",
        "-bsp1",  # Enable progress output
        delimiters=progress_delimiters,
    ):
        match = re.search(r"^\s*(\d+)%", segment)
        if match:
            yield int(match.group(1))


async def extract_minecraft_server(
    archive_path: str,
    target_path: str,
) -> AsyncGenerator[TaskProgress, None]:
    """
    Extract Minecraft server archive with progress updates.

    Yields TaskProgress for each step. The decompress step (10-80%)
    provides granular progress via extract_archive_stream.

    Args:
        archive_path: Path to the archive file
        target_path: Path where server files should be extracted

    Yields:
        TaskProgress: Progress updates for each step

    Raises:
        HTTPException: If extraction fails
    """
    archive_path = str(Path(archive_path).resolve())
    target_path = str(Path(target_path).resolve())

    def step_progress(step: str) -> TaskProgress:
        start, _ = STEP_PROGRESS[step]
        return TaskProgress(progress=start, message=f"{STEP_NAMES[step]}...")

    def map_decompress_progress(percent: int) -> int:
        """Map 0-100 from extract to 10-80 overall progress."""
        start, end = STEP_PROGRESS["decompress"]
        return start + (percent * (end - start)) // 100

    # Step 1: Check if archive exists (0%)
    yield step_progress("archiveFileCheck")
    if not await aioos.path.exists(archive_path):
        raise RuntimeError(f"压缩包不存在: {archive_path}")

    # Step 2: Check for server.properties in archive (5%)
    yield step_progress("serverPropertiesCheck")
    try:
        output = await exec_command(
            "7z",
            "l",
            archive_path,
            "server.properties",
            "-ba",
            "-r",
        )
    except Exception as e:
        error_msg = str(e)
        if (
            "7z: command not found" in error_msg
            or "No such file or directory" in error_msg
        ):
            raise RuntimeError("7z未安装或不可用")
        elif "Permission denied" in error_msg:
            raise RuntimeError("无权限访问压缩包文件")
        elif "is not supported archive" in error_msg or "Can not open" in error_msg:
            raise RuntimeError("压缩包文件损坏或格式不支持")
        else:
            raise RuntimeError("检查压缩包内容时发生错误")

    if "server.properties" not in output:
        raise RuntimeError("压缩包中未找到server.properties文件")

    # Step 3: Extract archive (10-80%) - with granular progress
    yield step_progress("decompress")
    temp_dir = f"{archive_path}.dir"
    try:
        server_uid, server_gid = await get_uid_gid(settings.server_path)
    except FileNotFoundError:
        raise RuntimeError(f"路径不存在: {settings.server_path}")

    try:
        async for percent in extract_archive_stream(archive_path, temp_dir):
            overall = map_decompress_progress(percent)
            yield TaskProgress(progress=overall, message=f"解压文件: {percent}%")
    except RuntimeError as e:
        error_msg = str(e)
        if "Permission denied" in error_msg:
            raise RuntimeError("无权限创建临时目录或解压文件")
        elif "No space left on device" in error_msg:
            raise RuntimeError("磁盘空间不足")
        else:
            raise RuntimeError("解压过程中发生错误")

    # Step 4: Change ownership (80%)
    yield step_progress("chown")
    try:
        await exec_command(
            "chown",
            f"{server_uid}:{server_gid}",
            temp_dir,
            "-R",
        )
    except Exception as e:
        error_msg = str(e)
        if "Operation not permitted" in error_msg:
            raise RuntimeError("无权限更改文件所有权")
        else:
            raise RuntimeError("更改文件所有权时发生错误")

    # Step 5: Find server.properties path (85%)
    yield step_progress("findPath")
    try:
        find_output = await exec_command(
            "find", temp_dir, "-name", "server.properties", "-print", "-quit"
        )
    except Exception as e:
        error_msg = str(e)
        if "Permission denied" in error_msg:
            raise RuntimeError("无权限搜索临时目录")
        else:
            raise RuntimeError("搜索server.properties时发生错误")

    if not find_output.strip():
        raise RuntimeError("解压后找不到server.properties文件")

    server_properties_path = Path(find_output.strip())
    server_dir = server_properties_path.parent

    # Clean up existing data directory
    if await aioos.path.exists(target_path):
        for item in await aioos.listdir(target_path):
            item_path = Path(target_path) / item
            if await aioos.path.isdir(str(item_path)):
                await async_rmtree(item_path)
            else:
                await aioos.remove(str(item_path))

    # Step 6: Move files (90%)
    yield step_progress("mv")
    try:
        # Ensure target directory exists
        await aioos.makedirs(target_path, exist_ok=True)

        # Move all files from server directory to target
        await exec_command(
            "find",
            str(server_dir),
            "-mindepth",
            "1",
            "-maxdepth",
            "1",
            "-exec",
            "mv",
            "{}",
            target_path,
            ";",
        )
    except Exception as e:
        error_msg = str(e)
        if "Permission denied" in error_msg:
            raise RuntimeError("无权限移动文件到目标目录")
        elif "No space left on device" in error_msg:
            raise RuntimeError("磁盘空间不足")
        else:
            raise RuntimeError("移动服务器文件时发生错误")

    # Step 7: Cleanup (95%)
    yield step_progress("remove")
    try:
        # Remove original archive
        await aioos.remove(archive_path)

        # Remove temporary directory
        await async_rmtree(Path(temp_dir))
    except Exception as e:
        error_msg = str(e)
        if "Permission denied" in error_msg:
            raise RuntimeError("无权限删除临时文件")
        else:
            raise RuntimeError("清理临时文件时发生错误")

    # Complete (100%)
    yield TaskProgress(progress=100, message="服务器填充完成", result={"success": True})
