"""
Archive file management endpoints.
Provides CRUD operations for archive files using the configured archive directory.
"""

from pathlib import Path
from typing import Optional

from aiofiles import os as aioos
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..background_tasks import TaskType, task_manager
from ..config import settings
from ..dependencies import get_current_user
from ..files import (
    CreateFileRequest,
    FileListResponse,
    RenameFileRequest,
    create_file_or_directory,
    delete_file_or_directory,
    get_file_items,
    rename_file_or_directory,
    upload_file,
)
from ..minecraft import docker_mc_manager
from ..models import UserPublic
from ..utils.compression import create_server_archive_stream
from ..utils.exec import exec_command

router = APIRouter(
    prefix="/archive",
    tags=["archive"],
)


class SHA256Response(BaseModel):
    sha256: str
    filename: str


class CreateArchiveRequest(BaseModel):
    server_id: str
    path: Optional[str] = None


class CreateArchiveResponse(BaseModel):
    task_id: str


def _get_archive_base_path() -> Path:
    """Get the base path for archive files."""
    # Ensure archive directory exists
    settings.archive_path.mkdir(parents=True, exist_ok=True)
    return settings.archive_path


# Archive file management endpoints
@router.get("", response_model=FileListResponse)
async def list_archive_files(
    path: str = "/", _: UserPublic = Depends(get_current_user)
):
    """List files and directories in the archive"""
    base_path = _get_archive_base_path()
    items = await get_file_items(base_path, path)

    return FileListResponse(items=items, current_path=path)


@router.get("/download")
async def download_archive_file(path: str, _: UserPublic = Depends(get_current_user)):
    """Download a specific archive file"""
    base_path = _get_archive_base_path()
    file_path = base_path / path.lstrip("/")

    # Validate file exists and is a file (not a directory)
    if not await aioos.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Archive file not found")

    if not await aioos.path.isfile(file_path):
        raise HTTPException(status_code=400, detail="Path is not a file")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/octet-stream",
    )


@router.post("/upload")
async def upload_archive_file(
    path: str = "/",
    file: UploadFile = File(...),
    allow_overwrite: bool = False,
    _: UserPublic = Depends(get_current_user),
):
    """Upload a file to the archive"""
    base_path = _get_archive_base_path()
    filename = await upload_file(base_path, path, file, allow_overwrite=allow_overwrite)

    return {"message": f"Archive file '{filename}' uploaded successfully"}


@router.post("/create")
async def create_archive_file_or_directory(
    create_request: CreateFileRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Create a new file or directory in the archive"""
    base_path = _get_archive_base_path()
    message = await create_file_or_directory(base_path, create_request)

    return {"message": message}


@router.delete("")
async def delete_archive_file_or_directory(
    path: str, _: UserPublic = Depends(get_current_user)
):
    """Delete an archive file or directory"""
    base_path = _get_archive_base_path()
    message = await delete_file_or_directory(base_path, path)

    return {"message": message}


@router.post("/rename")
async def rename_archive_file_or_directory(
    rename_request: RenameFileRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Rename an archive file or directory"""
    base_path = _get_archive_base_path()
    message = await rename_file_or_directory(base_path, rename_request)

    return {"message": message}


@router.get("/sha256", response_model=SHA256Response)
async def get_archive_file_sha256(path: str, _: UserPublic = Depends(get_current_user)):
    """Calculate SHA256 hash of a specific archive file"""
    base_path = _get_archive_base_path()
    file_path = base_path / path.lstrip("/")

    # Validate file exists and is a file (not a directory)
    if not await aioos.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Archive file not found")

    if not await aioos.path.isfile(file_path):
        raise HTTPException(status_code=400, detail="Path is not a file")

    # Execute sha256sum command
    output = await exec_command("sha256sum", str(file_path))

    # Parse output: "{hash} {file}" format, split by space and take first part
    parts = output.strip().split()
    if len(parts) < 1:
        raise HTTPException(status_code=500, detail="Invalid sha256sum output")

    sha256_hash = parts[0]

    return SHA256Response(sha256=sha256_hash, filename=file_path.name)


@router.post("/compress", response_model=CreateArchiveResponse)
async def create_server_archive_endpoint(
    request: CreateArchiveRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Create a compressed archive from server files as a background task."""
    instance = docker_mc_manager.get_instance(request.server_id)

    if not await instance.exists():
        raise HTTPException(
            status_code=404, detail=f"Server '{request.server_id}' not found"
        )

    if request.path is not None:
        if not request.path.startswith("/"):
            request.path = "/" + request.path

        data_dir = instance.get_data_path()
        if request.path != "/":
            target_path = data_dir / request.path.lstrip("/")
            if not await aioos.path.exists(target_path):
                raise HTTPException(
                    status_code=404,
                    detail=f"Path '{request.path}' not found in server data directory",
                )
        elif not await aioos.path.exists(data_dir):
            raise HTTPException(
                status_code=404, detail="Server data directory not found"
            )

    task_name = instance.get_name()
    if request.path:
        task_name += f"/{request.path.strip('/')}"

    result = task_manager.submit(
        task_type=TaskType.ARCHIVE_CREATE,
        name=task_name,
        task_generator=create_server_archive_stream(instance, request.path),
        server_id=request.server_id,
        cancellable=True,
    )

    return CreateArchiveResponse(task_id=result.task_id)
