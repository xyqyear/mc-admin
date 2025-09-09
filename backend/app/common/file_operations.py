"""
Common file operations utilities for both server files and archive files.
This module provides reusable functions for file management operations.
"""

import os
import shutil
from pathlib import Path
from typing import List, Literal

import aiofiles
from aiofiles import os as aioos
from asyncer import asyncify
from fastapi import HTTPException, UploadFile
from pydantic import BaseModel


# Pydantic models for file operations
class FileItem(BaseModel):
    name: str
    type: Literal["file", "directory"]
    size: int
    modified_at: float
    path: str


class FileListResponse(BaseModel):
    items: List[FileItem]
    current_path: str


class FileContent(BaseModel):
    content: str


class CreateFileRequest(BaseModel):
    name: str
    type: Literal["file", "directory"]
    path: str


class RenameFileRequest(BaseModel):
    old_path: str
    new_name: str


# Async utility functions
@asyncify
def _rmtree_async(path: Path):
    """Asynchronously remove a directory tree."""
    shutil.rmtree(path)


@asyncify
def _touch_async(path: Path):
    """Asynchronously create an empty file."""
    Path.touch(path)


@asyncify
def _chown_async(path: Path, uid: int, gid: int):
    """Asynchronously change ownership of a file or directory."""
    os.chown(path, uid, gid)


async def get_uid_gid(path: Path) -> tuple[int | None, int | None]:
    """Get the UID and GID of the specified path."""
    try:
        stat_info = await aioos.stat(path)
        return stat_info.st_uid, stat_info.st_gid
    except FileNotFoundError:
        return None, None


async def get_file_items(base_path: Path, current_path: str = "/") -> List[FileItem]:
    """Get list of files and directories in the specified path."""
    if current_path.startswith("/"):
        current_path = current_path[1:]  # Remove leading slash

    actual_path = base_path / current_path if current_path else base_path

    if not await aioos.path.exists(actual_path) or not await aioos.path.isdir(
        actual_path
    ):
        return []

    items = []

    try:
        file_list = await aioos.listdir(actual_path)
        for file_name in file_list:
            item_path = actual_path / file_name
            relative_path = item_path.relative_to(base_path)
            file_path = "/" + str(relative_path).replace("\\", "/")

            stat_result = await aioos.stat(item_path)

            if await aioos.path.isfile(item_path):
                size = stat_result.st_size
                file_type = "file"
            else:
                size = 0
                file_type = "directory"

            modified_at = stat_result.st_mtime

            items.append(
                FileItem(
                    name=file_name,
                    type=file_type,
                    size=size,
                    modified_at=modified_at,
                    path=file_path,
                )
            )
    except PermissionError:
        # Handle permission errors gracefully
        pass

    return items


async def get_file_content(base_path: Path, path: str) -> str:
    """Get content of a specific file."""
    file_path = base_path / path.lstrip("/")

    if not await aioos.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    if not await aioos.path.isfile(file_path):
        raise HTTPException(status_code=400, detail="Path is not a file")

    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
    except UnicodeDecodeError:
        try:
            async with aiofiles.open(file_path, "r", encoding="latin1") as f:
                content = await f.read()
        except Exception:
            raise HTTPException(status_code=400, detail="Unable to read file as text")

    return content


async def update_file_content(base_path: Path, path: str, content: str) -> None:
    """Update content of a specific file."""
    file_path = base_path / path.lstrip("/")

    if not await aioos.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    if not await aioos.path.isfile(file_path):
        raise HTTPException(status_code=400, detail="Path is not a file")

    async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
        await f.write(content)


async def upload_file(
    base_path: Path, path: str, file: UploadFile, allow_overwrite: bool = False
) -> str:
    """Upload a file to the specified path."""
    target_dir = base_path / path.lstrip("/")

    # Ensure target directory exists
    await aioos.makedirs(target_dir, exist_ok=True)

    if not await aioos.path.isdir(target_dir):
        raise HTTPException(status_code=400, detail="Target path is not a directory")

    file_path = target_dir / (file.filename or "unnamed_file")

    # Check if file already exists
    if not allow_overwrite and await aioos.path.exists(file_path):
        raise HTTPException(status_code=409, detail="File already exists")

    # Write file
    async with aiofiles.open(file_path, "wb") as f:
        while chunk := await file.read(10 * 1024 * 1024):
            await f.write(chunk)

    # Try to set ownership to match parent directory
    uid, gid = await get_uid_gid(base_path)
    if uid is not None and gid is not None:
        try:
            await _chown_async(file_path, uid, gid)
        except (OSError, PermissionError):
            # Ignore ownership errors (common in containers)
            pass

    return file.filename or "unnamed_file"


async def create_file_or_directory(
    base_path: Path, create_request: CreateFileRequest
) -> str:
    """Create a new file or directory."""
    target_path = base_path / create_request.path.lstrip("/") / create_request.name

    # Check if already exists
    if await aioos.path.exists(target_path):
        raise HTTPException(
            status_code=409,
            detail=f"{'Directory' if create_request.type == 'directory' else 'File'} already exists",
        )

    # Create parent directories if needed
    await aioos.makedirs(target_path.parent, exist_ok=True)

    if create_request.type == "directory":
        await aioos.mkdir(target_path)
        message = f"Directory '{create_request.name}' created successfully"
    elif create_request.type == "file":
        await _touch_async(target_path)
        message = f"File '{create_request.name}' created successfully"
    else:
        raise HTTPException(
            status_code=400, detail="Invalid type. Must be 'file' or 'directory'"
        )

    # Try to set ownership to match parent directory
    uid, gid = await get_uid_gid(base_path)
    if uid is not None and gid is not None:
        try:
            await _chown_async(target_path, uid, gid)
        except (OSError, PermissionError):
            # Ignore ownership errors (common in containers)
            pass

    return message


async def delete_file_or_directory(base_path: Path, path: str) -> str:
    """Delete a file or directory."""
    target_path = base_path / path.lstrip("/")

    if not await aioos.path.exists(target_path):
        raise HTTPException(status_code=404, detail="File or directory not found")

    if await aioos.path.isfile(target_path):
        await aioos.unlink(target_path)
        message = f"File '{target_path.name}' deleted successfully"
    elif await aioos.path.isdir(target_path):
        await _rmtree_async(target_path)
        message = f"Directory '{target_path.name}' deleted successfully"
    else:
        raise HTTPException(status_code=400, detail="Invalid path")

    return message


async def rename_file_or_directory(
    base_path: Path, rename_request: RenameFileRequest
) -> str:
    """Rename a file or directory."""
    old_path = base_path / rename_request.old_path.lstrip("/")
    new_path = old_path.parent / rename_request.new_name

    if not await aioos.path.exists(old_path):
        raise HTTPException(status_code=404, detail="File or directory not found")

    if await aioos.path.exists(new_path):
        raise HTTPException(status_code=409, detail="Target name already exists")

    await aioos.rename(old_path, new_path)

    item_type = "Directory" if await aioos.path.isdir(new_path) else "File"
    return f"{item_type} renamed successfully"
