"""
Utility for decompressing and extracting Minecraft server files.
"""

from pathlib import Path
from typing import AsyncGenerator, Literal

from aiofiles import os as aioos
from pydantic import BaseModel

from ..config import settings
from ..minecraft.utils import async_rmtree, exec_command


class DecompressionStepResult(BaseModel):
    """Result for each decompression step."""

    step: Literal["archiveFileCheck", "serverPropertiesCheck", "decompress", "chown", "findPath", "mv", "remove"]
    success: bool
    message: str
    error_details: str | None = None


class DecompressionError(Exception):
    """Custom exception for decompression errors."""

    def __init__(self, step: str, message: str, error_details: str | None = None):
        self.step = step
        self.message = message
        self.error_details = error_details
        super().__init__(f"{step}: {message}")


async def get_path_ownership(path: Path) -> tuple[int, int]:
    """Get the UID and GID of the specified path."""
    try:
        stat_info = await aioos.stat(path)
        return stat_info.st_uid, stat_info.st_gid
    except FileNotFoundError as e:
        raise DecompressionError("权限获取", f"路径不存在: {path}", str(e))


async def extract_minecraft_server(
    archive_path: str, target_path: str, test_uid: int | None = None, test_gid: int | None = None
) -> AsyncGenerator[DecompressionStepResult, None]:
    """
    Extract a Minecraft server archive to the target directory.

    Args:
        archive_path: Path to the archive file
        target_path: Path where server files should be extracted
        test_uid: Optional UID to run commands as (for testing only)
        test_gid: Optional GID to run commands as (for testing only)

    Yields:
        DecompressionStepResult: Progress updates for each step

    Raises:
        DecompressionError: If any step fails
    """
    # Ensure archive path is absolute
    archive_path = str(Path(archive_path).resolve())
    target_path = str(Path(target_path).resolve())

    # Step 1: Check if archive exists
    try:
        if not await aioos.path.exists(archive_path):
            raise DecompressionError("archiveFileCheck", f"压缩包不存在: {archive_path}")

        yield DecompressionStepResult(
            step="archiveFileCheck", success=True, message="压缩包文件存在"
        )
    except Exception as e:
        if isinstance(e, DecompressionError):
            raise
        raise DecompressionError("archiveFileCheck", "检查压缩包时发生错误", str(e))

    # Step 2: Check for server.properties in archive
    try:
        output = await exec_command(
            "7z", "l", archive_path, "server.properties", "-ba", "-r",
            uid=test_uid, gid=test_gid
        )
        if "server.properties" not in output:
            raise DecompressionError(
                "serverPropertiesCheck",
                "压缩包中未找到server.properties文件",
                "这不是一个有效的Minecraft服务器压缩包",
            )

        yield DecompressionStepResult(
            step="serverPropertiesCheck",
            success=True,
            message="已确认压缩包中存在server.properties",
        )
    except DecompressionError:
        raise
    except Exception as e:
        error_msg = str(e)
        if (
            "7z: command not found" in error_msg
            or "No such file or directory" in error_msg
        ):
            raise DecompressionError(
                "serverPropertiesCheck", "7z未安装或不可用", error_msg
            )
        elif "Permission denied" in error_msg:
            raise DecompressionError(
                "serverPropertiesCheck", "无权限访问压缩包文件", error_msg
            )
        elif "is not supported archive" in error_msg or "Can not open" in error_msg:
            raise DecompressionError(
                "serverPropertiesCheck", "压缩包文件损坏或格式不支持", error_msg
            )
        else:
            raise DecompressionError(
                "serverPropertiesCheck", "检查压缩包内容时发生错误", error_msg
            )

    # Step 3: Extract archive to temporary directory
    temp_dir = f"{archive_path}.dir"
    try:
        # Get server_path ownership for chown later
        server_uid, server_gid = await get_path_ownership(settings.server_path)

        # Extract archive
        await exec_command("7z", "x", archive_path, f"-o{temp_dir}", uid=test_uid, gid=test_gid)

        yield DecompressionStepResult(
            step="decompress", success=True, message=f"已解压至临时目录: {temp_dir}"
        )
    except Exception as e:
        error_msg = str(e)
        if "Permission denied" in error_msg:
            raise DecompressionError(
                "decompress", "无权限创建临时目录或解压文件", error_msg
            )
        elif "No space left on device" in error_msg:
            raise DecompressionError("decompress", "磁盘空间不足", error_msg)
        else:
            raise DecompressionError("decompress", "解压过程中发生错误", error_msg)

    # Step 4: Change ownership of extracted files
    try:
        await exec_command(
            "chown",
            f"{server_uid}:{server_gid}",
            temp_dir,
            "-R",
            uid=test_uid or server_uid,
            gid=test_gid or server_gid,
        )

        yield DecompressionStepResult(
            step="chown",
            success=True,
            message=f"已将文件所有权更改为 {server_uid}:{server_gid}",
        )
    except Exception as e:
        error_msg = str(e)
        if "Operation not permitted" in error_msg:
            raise DecompressionError("chown", "无权限更改文件所有权", error_msg)
        else:
            raise DecompressionError("chown", "更改文件所有权时发生错误", error_msg)

    # Step 5: Find server.properties and get its parent directory
    try:
        find_output = await exec_command("find", temp_dir, "-name", "server.properties", uid=test_uid, gid=test_gid)
        if not find_output.strip():
            raise DecompressionError(
                "findPath",
                "解压后找不到server.properties文件",
                "文件可能在解压过程中丢失",
            )

        server_properties_path = Path(find_output.strip().split("\n")[0])
        server_dir = server_properties_path.parent

        yield DecompressionStepResult(
            step="findPath", success=True, message=f"找到服务器文件目录: {server_dir}"
        )
    except DecompressionError:
        raise
    except Exception as e:
        error_msg = str(e)
        if "Permission denied" in error_msg:
            raise DecompressionError("findPath", "无权限搜索临时目录", error_msg)
        else:
            raise DecompressionError(
                "findPath", "搜索server.properties时发生错误", error_msg
            )

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
            uid=test_uid,
            gid=test_gid,
        )

        yield DecompressionStepResult(
            step="mv",
            success=True,
            message=f"服务器文件已移动到: {target_path}",
        )
    except Exception as e:
        error_msg = str(e)
        if "Permission denied" in error_msg:
            raise DecompressionError(
                "mv", "无权限移动文件到目标目录", error_msg
            )
        elif "No space left on device" in error_msg:
            raise DecompressionError(
                "mv", "磁盘空间不足", error_msg
            )
        else:
            raise DecompressionError(
                "mv", "移动服务器文件时发生错误", error_msg
            )

    # Step 7: Clean up temporary files
    try:
        # Remove original archive
        await aioos.remove(archive_path)

        # Remove temporary directory
        await async_rmtree(Path(temp_dir))

        yield DecompressionStepResult(
            step="remove", success=True, message="临时文件和压缩包已清理"
        )
    except Exception as e:
        error_msg = str(e)
        if "Permission denied" in error_msg:
            raise DecompressionError("remove", "无权限删除临时文件", error_msg)
        else:
            raise DecompressionError("remove", "清理临时文件时发生错误", error_msg)
