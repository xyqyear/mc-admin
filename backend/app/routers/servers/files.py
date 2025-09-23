from typing import List

from aiofiles import os as aioos
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ...common.file_operations import (
    CreateFileRequest,
    FileContent,
    FileListResponse,
    MultiFileUploadRequest,
    OverwritePolicy,
    RenameFileRequest,
    UploadConflictResponse,
    check_upload_conflicts,
    create_file_or_directory,
    delete_file_or_directory,
    get_file_content,
    get_file_items,
    rename_file_or_directory,
    set_upload_policy,
    update_file_content,
    upload_file,
    upload_multiple_files,
)
from ...dependencies import get_current_user
from ...minecraft import docker_mc_manager
from ...models import UserPublic

router = APIRouter(
    prefix="/servers",
    tags=["files"],
)


# File management endpoints
@router.get("/{server_id}/files", response_model=FileListResponse)
async def list_files(
    server_id: str, path: str = "/", _: UserPublic = Depends(get_current_user)
):
    """List files and directories in the specified server path"""
    try:
        instance = docker_mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = instance.get_data_path()
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
        instance = docker_mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = instance.get_data_path()
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
        instance = docker_mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = instance.get_data_path()
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
        instance = docker_mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = instance.get_data_path()
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
        instance = docker_mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = instance.get_data_path()
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
        instance = docker_mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = instance.get_data_path()
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
        instance = docker_mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = instance.get_data_path()
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
        instance = docker_mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = instance.get_data_path()
        message = await rename_file_or_directory(base_path, rename_request)

        return {"message": message}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rename: {str(e)}")


# Multi-file upload endpoints
@router.post("/{server_id}/files/upload/check", response_model=UploadConflictResponse)
async def check_multi_file_upload(
    server_id: str,
    path: str,
    upload_request: MultiFileUploadRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Check for conflicts before multi-file upload"""
    try:
        instance = docker_mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = instance.get_data_path()
        conflict_response = await check_upload_conflicts(
            base_path, path, upload_request
        )

        return conflict_response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to check upload conflicts: {str(e)}"
        )


@router.post("/{server_id}/files/upload/policy")
async def set_multi_file_upload_policy(
    server_id: str,
    session_id: str,
    policy: OverwritePolicy,
    reusable: bool = False,
    _: UserPublic = Depends(get_current_user),
):
    """Set the overwrite policy for a multi-file upload session"""
    try:
        instance = docker_mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        await set_upload_policy(session_id, policy, reusable)

        return {"message": "Upload policy set successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to set upload policy: {str(e)}"
        )


@router.post("/{server_id}/files/upload/multiple")
async def upload_multiple_files_endpoint(
    server_id: str,
    session_id: str,
    path: str,
    files: List[UploadFile] = File(...),
    _: UserPublic = Depends(get_current_user),
):
    """Upload multiple files using a prepared session"""
    try:
        instance = docker_mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        base_path = instance.get_data_path()
        results = await upload_multiple_files(base_path, session_id, path, files)

        return results

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to upload multiple files: {str(e)}"
        )
