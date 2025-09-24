"""
Utility for compressing Minecraft server files and directories.
"""

from datetime import datetime
from typing import Optional

from aiofiles import os as aioos
from fastapi import HTTPException

from app.minecraft.instance import MCInstance

from ..config import settings
from .exec import exec_command


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


async def create_server_archive(
    instance: MCInstance, relative_path: Optional[str] = None
) -> str:
    """
    Create a compressed archive of server files.

    Args:
        server_name: Name of the server
        server_project_path: Path to the server's project directory
        relative_path: Optional relative path within the server to compress (relative to data directory)
                      If None, compresses the entire server directory
                      If provided, should start with "/" and be relative to server_project_path/data

    Returns:
        Filename of the created archive

    Raises:
        HTTPException: If archive creation fails
    """
    # Ensure archive directory exists
    archive_base_path = settings.archive_path.resolve()
    await aioos.makedirs(archive_base_path, exist_ok=True)

    # Generate archive filename
    archive_filename = _generate_archive_filename(instance.get_name(), relative_path)
    archive_path = archive_base_path / archive_filename

    # Determine source path
    if relative_path is None:
        # Compress entire server directory
        source_path = instance.get_project_path()
    else:
        data_dir = instance.get_data_path()
        clean_relative_path = relative_path.lstrip("/")

        if clean_relative_path == "":
            source_path = data_dir
        else:
            source_path = data_dir / clean_relative_path

    # Validate source path exists
    if not await aioos.path.exists(source_path):
        raise HTTPException(
            status_code=404, detail=f"Source path does not exist: {source_path}"
        )

    try:
        # Create 7z archive
        # Use parent directory as working directory and only specify the relative name
        # This ensures the archive doesn't contain the full filesystem path
        source_parent = source_path.parent
        source_name = source_path.name

        # Use 7z for high compression ratio
        await exec_command(
            "7z", "a", "-t7z", str(archive_path), source_name, cwd=str(source_parent)
        )

        # Verify archive was created
        if not await aioos.path.exists(archive_path):
            raise HTTPException(
                status_code=500, detail="Archive was not created successfully"
            )

        return archive_filename

    except Exception as e:
        error_msg = str(e)

        # Clean up partial archive if it exists
        if await aioos.path.exists(archive_path):
            try:
                await aioos.remove(archive_path)
            except OSError:
                pass  # Ignore cleanup errors

        if "Permission denied" in error_msg:
            raise HTTPException(
                status_code=403, detail="Permission denied while creating archive"
            )
        elif "No space left on device" in error_msg:
            raise HTTPException(
                status_code=507, detail="Insufficient disk space to create archive"
            )
        elif (
            "7z: command not found" in error_msg
            or "No such file or directory" in error_msg
        ):
            raise HTTPException(
                status_code=500, detail="7z command not available on system"
            )
        else:
            raise HTTPException(
                status_code=500, detail=f"Failed to create archive: {error_msg}"
            )
