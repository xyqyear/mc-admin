from aiofiles import os as aioos
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.auth.schemas import UserPublic

from ...background_tasks import TaskType, get_task_manager
from ...dependencies import get_current_user
from ...files import (
    CreateFileRequest,
    FileContent,
    FileListResponse,
    FileSearchRequest,
    FileSearchResponse,
    MultiFileUploadRequest,
    OverwritePolicy,
    OwnershipRestoreTaskResponse,
    RenameFileRequest,
    UploadConflictResponse,
    check_upload_conflicts,
    get_file_content,
    get_file_items,
    restore_tree_ownership_task,
    search_files,
    set_upload_policy,
)
from ...files.application import FileApplication
from ...files.paths import resolve_file_path
from ...minecraft import get_docker_mc_manager
from .admission import admit_server_write

router = APIRouter(
    prefix="/servers",
    tags=["files"],
    dependencies=[Depends(admit_server_write)],
)


# File management endpoints
@router.get("/{server_id}/files", response_model=FileListResponse)
async def list_files(
    server_id: str, path: str = "/", _: UserPublic = Depends(get_current_user)
):
    """List files and directories in the specified server path"""
    instance = get_docker_mc_manager().get_instance(server_id)

    # Check if server exists
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    base_path = instance.get_data_path()
    items = await get_file_items(base_path, path)

    return FileListResponse(items=items, current_path=path)


@router.get("/{server_id}/files/content")
async def get_file_content_endpoint(
    server_id: str, path: str, _: UserPublic = Depends(get_current_user)
):
    """Get content of a specific file"""
    instance = get_docker_mc_manager().get_instance(server_id)

    # Check if server exists
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    base_path = instance.get_data_path()
    content = await get_file_content(base_path, path)

    return FileContent(content=content)


@router.post("/{server_id}/files/content")
async def update_file_content_endpoint(
    server_id: str,
    path: str,
    file_content: FileContent,
    _: UserPublic = Depends(get_current_user),
):
    """Update content of a specific file"""
    instance = get_docker_mc_manager().get_instance(server_id)

    # Check if server exists
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    await FileApplication(instance, server_id, _.id).update(path, file_content.content)

    return {"message": "File updated successfully"}


@router.get("/{server_id}/files/download")
async def download_file(
    server_id: str, path: str, _: UserPublic = Depends(get_current_user)
):
    """Download a specific file"""
    instance = get_docker_mc_manager().get_instance(server_id)

    # Check if server exists
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    base_path = instance.get_data_path()
    file_path = await resolve_file_path(base_path, path)

    if not await aioos.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    if not await aioos.path.isfile(file_path):
        raise HTTPException(status_code=400, detail="Path is not a file")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/octet-stream",
    )


@router.post("/{server_id}/files/create")
async def create_file_or_directory_endpoint(
    server_id: str,
    create_request: CreateFileRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Create a new file or directory"""
    instance = get_docker_mc_manager().get_instance(server_id)

    # Check if server exists
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    message = await FileApplication(instance, server_id, _.id).create(create_request)

    return {"message": message}


@router.delete("/{server_id}/files")
async def delete_file_or_directory_endpoint(
    server_id: str, path: str, _: UserPublic = Depends(get_current_user)
):
    """Delete a file or directory"""
    instance = get_docker_mc_manager().get_instance(server_id)

    # Check if server exists
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    message = await FileApplication(instance, server_id, _.id).delete(path)

    return {"message": message}


@router.post("/{server_id}/files/rename")
async def rename_file_or_directory_endpoint(
    server_id: str,
    rename_request: RenameFileRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Rename a file or directory"""
    instance = get_docker_mc_manager().get_instance(server_id)

    # Check if server exists
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    message = await FileApplication(instance, server_id, _.id).rename(rename_request)

    return {"message": message}


@router.post(
    "/{server_id}/files/ownership/restore",
    response_model=OwnershipRestoreTaskResponse,
)
async def restore_file_ownership_endpoint(
    server_id: str, _: UserPublic = Depends(get_current_user)
):
    """Restore all server files to the server root owner as a background task."""
    instance = get_docker_mc_manager().get_instance(server_id)

    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    base_path = instance.get_data_path()
    if not await aioos.path.exists(base_path):
        raise HTTPException(status_code=404, detail="服务器数据目录不存在")

    application = FileApplication(instance, server_id, _.id)
    claims = await application.claims([base_path])
    result = await get_task_manager().submit_durable(
        task_type=TaskType.FILE_OWNERSHIP_REPAIR,
        name=instance.get_name(),
        task_generator=application.task([base_path], restore_tree_ownership_task(base_path), claims=claims),
        claims=claims,
        server_id=server_id,
        cancellable=False,
        actor_id=_.id,
    )

    return OwnershipRestoreTaskResponse(task_id=result.task_id)


# Multi-file upload endpoints
@router.post("/{server_id}/files/upload/check", response_model=UploadConflictResponse)
async def check_multi_file_upload(
    server_id: str,
    path: str,
    upload_request: MultiFileUploadRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Check for conflicts before multi-file upload"""
    instance = get_docker_mc_manager().get_instance(server_id)

    # Check if server exists
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    base_path = instance.get_data_path()
    conflict_response = await check_upload_conflicts(base_path, path, upload_request)

    return conflict_response


@router.post("/{server_id}/files/upload/policy")
async def set_multi_file_upload_policy(
    server_id: str,
    session_id: str,
    policy: OverwritePolicy,
    reusable: bool = False,
    _: UserPublic = Depends(get_current_user),
):
    """Set the overwrite policy for a multi-file upload session"""
    instance = get_docker_mc_manager().get_instance(server_id)

    # Check if server exists
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    await set_upload_policy(session_id, policy, reusable)

    return {"message": "Upload policy set successfully"}


@router.post("/{server_id}/files/upload/multiple")
async def upload_multiple_files_endpoint(
    server_id: str,
    session_id: str,
    path: str,
    files: list[UploadFile] = File(...),
    _: UserPublic = Depends(get_current_user),
):
    """Upload multiple files using a prepared session"""
    instance = get_docker_mc_manager().get_instance(server_id)

    # Check if server exists
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    results = await FileApplication(instance, server_id, _.id).upload(session_id, path, files)

    return results


# File search endpoint
@router.post("/{server_id}/files/search", response_model=FileSearchResponse)
async def search_server_files(
    server_id: str,
    search_request: FileSearchRequest,
    path: str = "/",
    _: UserPublic = Depends(get_current_user),
):
    """Search for files in the specified server path using regex patterns"""
    instance = get_docker_mc_manager().get_instance(server_id)

    # Check if server exists
    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    # Get base path and construct search path
    base_path = instance.get_data_path()
    if path.strip() == "/" or not path.strip():
        search_path = base_path
        search_path_str = "/"
    else:
        search_path = base_path / path.lstrip("/")
        search_path_str = "/" + path.lstrip("/")

    search_path = await resolve_file_path(base_path, path)
    # Perform search
    results = await search_files(search_path, search_request)

    return FileSearchResponse(
        query=search_request,
        results=results,
        total_count=len(results),
        search_path=search_path_str,
    )
