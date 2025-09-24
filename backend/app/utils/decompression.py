"""
Utility for decompressing and extracting Minecraft server files.
"""

from pathlib import Path
from typing import Literal

from aiofiles import os as aioos
from fastapi import HTTPException
from pydantic import BaseModel

from ..config import settings
from ..files.utils import get_uid_gid
from .exec import async_rmtree, exec_command


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


async def extract_minecraft_server(
    archive_path: str,
    target_path: str,
) -> None:
    """
    Extract a Minecraft server archive to the target directory.

    Args:
        archive_path: Path to the archive file
        target_path: Path where server files should be extracted
        test_uid: Optional UID to run commands as (for testing only)
        test_gid: Optional GID to run commands as (for testing only)

    Yields:
        DecompressionStepResult: Progress updates for each step

    """
    # Ensure archive path is absolute
    archive_path = str(Path(archive_path).resolve())
    target_path = str(Path(target_path).resolve())

    # Step 1: Check if archive exists
    if not await aioos.path.exists(archive_path):
        raise HTTPException(
            status_code=404,
            detail=f"压缩包不存在: {archive_path}",
        )

    # Step 2: Check for server.properties in archive
    try:
        output = await exec_command(
            "7z",
            "l",
            archive_path,
            "server.properties",
            "-ba",
            "-r",
        )
        if "server.properties" not in output:
            raise HTTPException(
                status_code=400,
                detail="压缩包中未找到server.properties文件",
            )
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        if (
            "7z: command not found" in error_msg
            or "No such file or directory" in error_msg
        ):
            raise HTTPException(
                status_code=500,
                detail="7z未安装或不可用",
            )
        elif "Permission denied" in error_msg:
            raise HTTPException(
                status_code=403,
                detail="无权限访问压缩包文件",
            )
        elif "is not supported archive" in error_msg or "Can not open" in error_msg:
            raise HTTPException(
                status_code=400,
                detail="压缩包文件损坏或格式不支持",
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="检查压缩包内容时发生错误",
            )

    # Step 3: Extract archive to temporary directory
    temp_dir = f"{archive_path}.dir"
    try:
        # Get server_path ownership for chown later
        server_uid, server_gid = await get_uid_gid(settings.server_path)
        if server_uid is None or server_gid is None:
            raise HTTPException(
                status_code=500,
                detail=f"路径不存在: {settings.server_path}",
            )

        # Extract archive
        await exec_command("7z", "x", archive_path, f"-o{temp_dir}")
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        if "Permission denied" in error_msg:
            raise HTTPException(
                status_code=403,
                detail="无权限创建临时目录或解压文件",
            )
        elif "No space left on device" in error_msg:
            raise HTTPException(
                status_code=507,
                detail="磁盘空间不足",
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="解压过程中发生错误",
            )

    # Step 4: Change ownership of extracted files
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
            raise HTTPException(
                status_code=403,
                detail="无权限更改文件所有权",
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="更改文件所有权时发生错误",
            )

    # Step 5: Find server.properties and get its parent directory
    try:
        find_output = await exec_command(
            "find", temp_dir, "-name", "server.properties", "-print", "-quit"
        )
        if not find_output.strip():
            raise HTTPException(
                status_code=400,
                detail="解压后找不到server.properties文件",
            )

        server_properties_path = Path(find_output.strip())
        server_dir = server_properties_path.parent
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        if "Permission denied" in error_msg:
            raise HTTPException(
                status_code=403,
                detail="无权限搜索临时目录",
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="搜索server.properties时发生错误",
            )

    # Clean up existing data directory
    if await aioos.path.exists(target_path):
        for item in await aioos.listdir(target_path):
            if await aioos.path.isdir(item):
                await async_rmtree(Path(item))
            else:
                await aioos.remove(item)

    # Step 6: Move server files to target directory
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
            raise HTTPException(
                status_code=403,
                detail="无权限移动文件到目标目录",
            )
        elif "No space left on device" in error_msg:
            raise HTTPException(
                status_code=507,
                detail="磁盘空间不足",
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="移动服务器文件时发生错误",
            )

    # Step 7: Clean up temporary files
    try:
        # Remove original archive
        await aioos.remove(archive_path)

        # Remove temporary directory
        await async_rmtree(Path(temp_dir))
    except Exception as e:
        error_msg = str(e)
        if "Permission denied" in error_msg:
            raise HTTPException(
                status_code=403,
                detail="无权限删除临时文件",
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="清理临时文件时发生错误",
            )
