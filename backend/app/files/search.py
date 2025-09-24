"""
File search utilities using fd command for fast file searching.
"""

from datetime import datetime
from pathlib import Path
from typing import List

from aiofiles import os as aioos
from fastapi import HTTPException

from ..config import settings
from ..utils.exec import exec_command
from .types import FileSearchRequest, FileType, SearchFileItem


async def _run_fd_command(search_request: FileSearchRequest, search_path: Path) -> str:
    """Run fd command with search parameters and return output"""
    cmd = [str(settings.fd_binary_path), "--unrestricted", "--absolute-path"]

    # Case sensitivity
    if search_request.ignore_case:
        cmd.append("--ignore-case")
    else:
        cmd.append("--case-sensitive")

    # Size filters
    if search_request.min_size is not None:
        cmd.extend(["--size", f"+{search_request.min_size}b"])
    if search_request.max_size is not None:
        cmd.extend(["--size", f"-{search_request.max_size}b"])

    # Date filters
    if search_request.newer_than is not None:
        cmd.extend(["--change-newer-than", search_request.newer_than.isoformat()])
    if search_request.older_than is not None:
        cmd.extend(["--change-older-than", search_request.older_than.isoformat()])

    # Add regex pattern and search path
    cmd.append(search_request.regex)
    cmd.append(str(search_path))

    # Execute with stat format
    cmd.extend(["-x", "stat", "--format=%s,%y,%F,%n"])

    try:
        return await exec_command(*cmd)
    except RuntimeError as e:
        error_message = str(e)
        if "Failed to exec command:" in error_message:
            # Extract the actual error from the exec_command format
            error_details = error_message.split("Failed to exec command:")[1].strip()
            raise HTTPException(
                status_code=500, detail=f"Search command failed: {error_details}"
            )
        raise HTTPException(
            status_code=500, detail=f"Search operation failed: {error_message}"
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="fd command not found. Please ensure fd-find is installed.",
        )


def _parse_fd_output(output: str, base_path: Path) -> List[SearchFileItem]:
    """Parse fd command output into SearchFileItem objects"""
    if not output.strip():
        return []

    results = []
    for line in output.strip().split("\n"):
        if not line.strip():
            continue

        # Split into exactly 5 parts: size, date+time+timezone, file_type, filename
        # Format: "size,2025-09-18 02:00:04.117123764 +0800,regular file,/path/to/file"
        parts = line.split(",", 3)  # Split into 4 parts maximum
        if len(parts) != 4:
            continue  # Skip malformed lines

        try:
            size_str, datetime_str, file_type_str, filename = parts

            # Parse size
            size = int(size_str)

            # Parse datetime (format: "2025-09-18 02:00:04.117123764 +0800")
            try:
                # Replace space before timezone with 'T' for ISO format, then handle timezone
                # "2025-09-18 02:00:04.117123764 +0800" -> "2025-09-18T02:00:04.117123764+08:00"
                datetime_parts = datetime_str.rsplit(
                    " ", 1
                )  # Split date/time and timezone
                if len(datetime_parts) == 2:
                    dt_part, tz_part = datetime_parts
                    # Convert timezone from "+0800" to "+08:00" format
                    if len(tz_part) == 5 and (tz_part[0] in "+-"):
                        tz_formatted = f"{tz_part[:3]}:{tz_part[3:]}"
                        iso_datetime = f"{dt_part.replace(' ', 'T')}{tz_formatted}"
                    else:
                        iso_datetime = dt_part.replace(" ", "T")
                else:
                    iso_datetime = datetime_str.replace(" ", "T")

                modified_at = datetime.fromisoformat(iso_datetime)
            except ValueError:
                # Fallback: try parsing without timezone
                try:
                    dt_part = (
                        datetime_str.split(" +")[0]
                        if " +" in datetime_str
                        else datetime_str.split(" -")[0]
                        if " -" in datetime_str
                        else datetime_str
                    )
                    modified_at = datetime.fromisoformat(dt_part.replace(" ", "T"))
                except ValueError:
                    continue  # Skip this line if datetime parsing fails

            # Parse file type
            if "regular file" in file_type_str or "regular empty file" in file_type_str:
                file_type = FileType.FILE
            elif "directory" in file_type_str:
                file_type = FileType.DIRECTORY
            else:
                file_type = FileType.OTHER

            # Convert absolute path to relative path
            abs_path = Path(filename)
            try:
                relative_path = abs_path.relative_to(base_path)
                path_str = "/" + str(relative_path).replace("\\", "/")
            except ValueError:
                # Path is not under base_path, skip it
                continue

            # Get filename only
            name = abs_path.name

            results.append(
                SearchFileItem(
                    name=name,
                    path=path_str,
                    type=file_type,
                    size=size,
                    modified_at=modified_at,
                )
            )

        except (ValueError, IndexError):
            # Skip malformed lines
            continue

    return results


async def search_files(
    base_path: Path, search_request: FileSearchRequest
) -> List[SearchFileItem]:
    """Search for files using fd command"""
    if not await aioos.path.exists(base_path):
        raise HTTPException(status_code=404, detail="Search path does not exist")

    if not await aioos.path.isdir(base_path):
        raise HTTPException(status_code=400, detail="Search path is not a directory")

    # Run fd command
    output = await _run_fd_command(search_request, base_path)

    # Parse results
    results = _parse_fd_output(output, base_path)

    return results
