import shutil
from pathlib import Path
from typing import List, Literal

import aiofiles
from aiofiles import os as aioos
from asyncer import asyncify
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ...config import settings
from ...dependencies import get_current_user
from ...minecraft import DockerMCManager
from ...models import UserPublic

router = APIRouter(
    prefix="/servers",
    tags=["files"],
)

# Initialize the Docker MC Manager
mc_manager = DockerMCManager(settings.server_path)


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


# Helper functions for file management
def _get_server_data_path(instance) -> Path:
    """Get the data path for the server instance."""
    return instance.get_project_path() / "data"


@asyncify
def _rmtree_async(path: Path):
    shutil.rmtree(path)


async def _get_file_items(base_path: Path, current_path: str = "/") -> List[FileItem]:
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


# File management endpoints
@router.get("/{server_id}/files", response_model=FileListResponse)
async def list_files(
    server_id: str, path: str = "/", _: UserPublic = Depends(get_current_user)
):
    """List files and directories in the specified server path"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = _get_server_data_path(instance)
        items = await _get_file_items(base_path, path)

        return FileListResponse(items=items, current_path=path)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")


@router.get("/{server_id}/files/content")
async def get_file_content(
    server_id: str, path: str, _: UserPublic = Depends(get_current_user)
):
    """Get content of a specific file"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = _get_server_data_path(instance)
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
                raise HTTPException(
                    status_code=400, detail="Unable to read file as text"
                )

        return FileContent(content=content)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")


@router.post("/{server_id}/files/content")
async def update_file_content(
    server_id: str,
    path: str,
    file_content: FileContent,
    _: UserPublic = Depends(get_current_user),
):
    """Update content of a specific file"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = _get_server_data_path(instance)
        file_path = base_path / path.lstrip("/")

        if not await aioos.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")

        if not await aioos.path.isfile(file_path):
            raise HTTPException(status_code=400, detail="Path is not a file")

        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(file_content.content)

        return {"message": "File updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update file: {str(e)}")


@router.get("/{server_id}/files/download")
async def download_file(server_id: str, path: str, _: UserPublic = Depends(get_current_user)):
    """Download a specific file"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = _get_server_data_path(instance)
        file_path = base_path / path.lstrip("/")

        if not await aioos.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")

        if not await aioos.path.isfile(file_path):
            raise HTTPException(status_code=400, detail="Path is not a file")

        return FileResponse(
            path=str(file_path),
            filename=file_path.name,
            media_type="application/octet-stream",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to download file: {str(e)}"
        )


@router.post("/{server_id}/files/upload")
async def upload_file(
    server_id: str,
    path: str = "/",
    file: UploadFile = File(...),
    _: UserPublic = Depends(get_current_user),
):
    """Upload a file to the specified server path"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = _get_server_data_path(instance)
        target_dir = base_path / path.lstrip("/")

        # Ensure target directory exists
        await aioos.makedirs(target_dir, exist_ok=True)

        if not await aioos.path.isdir(target_dir):
            raise HTTPException(
                status_code=400, detail="Target path is not a directory"
            )

        file_path = target_dir / (file.filename or "unnamed_file")

        # Check if file already exists
        if await aioos.path.exists(file_path):
            raise HTTPException(status_code=409, detail="File already exists")

        # Write file
        async with aiofiles.open(file_path, "wb") as f:
            content = await file.read()
            await f.write(content)

        return {"message": f"File '{file.filename}' uploaded successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")


@router.post("/{server_id}/files/create")
async def create_file_or_directory(
    server_id: str,
    create_request: CreateFileRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Create a new file or directory"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = _get_server_data_path(instance)
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
            async with aiofiles.open(target_path, "w"):
                pass  # Create empty file
            message = f"File '{create_request.name}' created successfully"
        else:
            raise HTTPException(
                status_code=400, detail="Invalid type. Must be 'file' or 'directory'"
            )

        return {"message": message}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create {'directory' if create_request.type == 'directory' else 'file'}: {str(e)}",
        )


@router.delete("/{server_id}/files")
async def delete_file_or_directory(
    server_id: str, path: str, _: UserPublic = Depends(get_current_user)
):
    """Delete a file or directory"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = _get_server_data_path(instance)
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

        return {"message": message}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {str(e)}")


@router.post("/{server_id}/files/rename")
async def rename_file_or_directory(
    server_id: str,
    rename_request: RenameFileRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Rename a file or directory"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = _get_server_data_path(instance)
        old_path = base_path / rename_request.old_path.lstrip("/")
        new_path = old_path.parent / rename_request.new_name

        if not await aioos.path.exists(old_path):
            raise HTTPException(status_code=404, detail="File or directory not found")

        if await aioos.path.exists(new_path):
            raise HTTPException(status_code=409, detail="Target name already exists")

        await aioos.rename(old_path, new_path)

        item_type = "Directory" if await aioos.path.isdir(new_path) else "File"
        return {"message": f"{item_type} renamed successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rename: {str(e)}")
