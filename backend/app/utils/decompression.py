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


async def get_path_ownership(path: Path) -> tuple[int, int] | None:
    """Get the UID and GID of the specified path."""
    try:
        stat_info = await aioos.stat(path)
        return stat_info.st_uid, stat_info.st_gid
    except FileNotFoundError:
        return None


async def extract_minecraft_server(
    archive_path: str,
    target_path: str,
    test_uid: int | None = None,
    test_gid: int | None = None,
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

    """
    # Ensure archive path is absolute
    archive_path = str(Path(archive_path).resolve())
    target_path = str(Path(target_path).resolve())

    # Step 1: Check if archive exists
    try:
        if not await aioos.path.exists(archive_path):
            yield DecompressionStepResult(
                step="archiveFileCheck",
                success=False,
                message=f"压缩包不存在: {archive_path}",
            )
            return

        yield DecompressionStepResult(
            step="archiveFileCheck", success=True, message="压缩包文件存在"
        )
    except Exception as e:
        yield DecompressionStepResult(
            step="archiveFileCheck",
            success=False,
            message=str(e),
        )
        return

    # Step 2: Check for server.properties in archive
    try:
        output = await exec_command(
            "7z",
            "l",
            archive_path,
            "server.properties",
            "-ba",
            "-r",
            uid=test_uid,
            gid=test_gid,
        )
        if "server.properties" not in output:
            yield DecompressionStepResult(
                step="serverPropertiesCheck",
                success=False,
                message="压缩包中未找到server.properties文件",
            )
            return

        yield DecompressionStepResult(
            step="serverPropertiesCheck",
            success=True,
            message="已确认压缩包中存在server.properties",
        )
    except Exception as e:
        error_msg = str(e)
        if (
            "7z: command not found" in error_msg
            or "No such file or directory" in error_msg
        ):
            yield DecompressionStepResult(
                step="serverPropertiesCheck",
                success=False,
                message="7z未安装或不可用",
            )
        elif "Permission denied" in error_msg:
            yield DecompressionStepResult(
                step="serverPropertiesCheck",
                success=False,
                message="无权限访问压缩包文件",
            )
        elif "is not supported archive" in error_msg or "Can not open" in error_msg:
            yield DecompressionStepResult(
                step="serverPropertiesCheck",
                success=False,
                message="压缩包文件损坏或格式不支持",
            )
        else:
            yield DecompressionStepResult(
                step="serverPropertiesCheck",
                success=False,
                message="检查压缩包内容时发生错误",
            )
        return

    # Step 3: Extract archive to temporary directory
    temp_dir = f"{archive_path}.dir"
    try:
        # Get server_path ownership for chown later
        ownership_result = await get_path_ownership(settings.server_path)
        if ownership_result is None:
            yield DecompressionStepResult(
                step="decompress",
                success=False,
                message=f"路径不存在: {settings.server_path}",
            )
            return
        server_uid, server_gid = ownership_result

        # Extract archive
        await exec_command(
            "7z", "x", archive_path, f"-o{temp_dir}", uid=test_uid, gid=test_gid
        )

        yield DecompressionStepResult(
            step="decompress", success=True, message=f"已解压至临时目录: {temp_dir}"
        )
    except Exception as e:
        error_msg = str(e)
        if "Permission denied" in error_msg:
            yield DecompressionStepResult(
                step="decompress",
                success=False,
                message="无权限创建临时目录或解压文件",
            )
        elif "No space left on device" in error_msg:
            yield DecompressionStepResult(
                step="decompress",
                success=False,
                message="磁盘空间不足",
            )
        else:
            yield DecompressionStepResult(
                step="decompress",
                success=False,
                message="解压过程中发生错误",
            )
        return

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
            yield DecompressionStepResult(
                step="chown",
                success=False,
                message="无权限更改文件所有权",
            )
        else:
            yield DecompressionStepResult(
                step="chown",
                success=False,
                message="更改文件所有权时发生错误",
            )
        return

    # Step 5: Find server.properties and get its parent directory
    try:
        find_output = await exec_command(
            "find", temp_dir, "-name", "server.properties", uid=test_uid, gid=test_gid
        )
        if not find_output.strip():
            yield DecompressionStepResult(
                step="findPath",
                success=False,
                message="解压后找不到server.properties文件",
            )
            return

        server_properties_path = Path(find_output.strip().split("\n")[0])
        server_dir = server_properties_path.parent

        yield DecompressionStepResult(
            step="findPath", success=True, message=f"找到服务器文件目录: {server_dir}"
        )
    except Exception as e:
        error_msg = str(e)
        if "Permission denied" in error_msg:
            yield DecompressionStepResult(
                step="findPath",
                success=False,
                message="无权限搜索临时目录",
            )
        else:
            yield DecompressionStepResult(
                step="findPath",
                success=False,
                message="搜索server.properties时发生错误",
            )
        return

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
            yield DecompressionStepResult(
                step="mv",
                success=False,
                message="无权限移动文件到目标目录",
            )
        elif "No space left on device" in error_msg:
            yield DecompressionStepResult(
                step="mv",
                success=False,
                message="磁盘空间不足",
            )
        else:
            yield DecompressionStepResult(
                step="mv",
                success=False,
                message="移动服务器文件时发生错误",
            )
        return

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
            yield DecompressionStepResult(
                step="remove",
                success=False,
                message="无权限删除临时文件",
            )
        else:
            yield DecompressionStepResult(
                step="remove",
                success=False,
                message="清理临时文件时发生错误",
            )
        return
