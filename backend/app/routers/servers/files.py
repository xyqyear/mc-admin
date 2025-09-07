from pathlib import Path

from aiofiles import os as aioos
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ...common.file_operations import (
    FileContent,
    FileListResponse,
    CreateFileRequest,
    RenameFileRequest,
    get_file_items,
    get_file_content,
    update_file_content,
    upload_file,
    create_file_or_directory,
    delete_file_or_directory,
    rename_file_or_directory,
)
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


# Helper functions for file management
def _get_server_data_path(instance) -> Path:
    """Get the data path for the server instance."""
    return instance.get_project_path() / "data"


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
        items = await get_file_items(base_path, path)

        return FileListResponse(items=items, current_path=path)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")


@router.get("/{server_id}/files/content")
async def get_file_content_endpoint(
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
        content = await get_file_content(base_path, path)

        return FileContent(content=content)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")


@router.post("/{server_id}/files/content")
async def update_file_content_endpoint(
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
        await update_file_content(base_path, path, file_content.content)

        return {"message": "File updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update file: {str(e)}")


@router.get("/{server_id}/files/download")
async def download_file(
    server_id: str, path: str, _: UserPublic = Depends(get_current_user)
):
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
async def upload_file_endpoint(
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
        filename = await upload_file(base_path, path, file, allow_overwrite=False)

        return {"message": f"File '{filename}' uploaded successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")


@router.post("/{server_id}/files/create")
async def create_file_or_directory_endpoint(
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
        message = await create_file_or_directory(base_path, create_request)

        return {"message": message}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create {'directory' if create_request.type == 'directory' else 'file'}: {str(e)}",
        )


@router.delete("/{server_id}/files")
async def delete_file_or_directory_endpoint(
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
        message = await delete_file_or_directory(base_path, path)

        return {"message": message}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {str(e)}")


@router.post("/{server_id}/files/rename")
async def rename_file_or_directory_endpoint(
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
        message = await rename_file_or_directory(base_path, rename_request)

        return {"message": message}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rename: {str(e)}")
