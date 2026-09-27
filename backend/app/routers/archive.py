"""
Archive file management endpoints.
Provides CRUD operations for archive files using the configured archive directory.
"""

from pathlib import Path

from aiofiles import os as aioos
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse

from app.archive.api_models import CreateArchiveRequest, CreateArchiveResponse
from app.auth.schemas import UserPublic

from ..archive.application import (
    ArchiveApplication,
    compress,
    is_archive_stage,
    prepare_compression,
)
from ..archive.uploads import (
    ArchiveUploadChunkResponse,
    ArchiveUploadInitRequest,
    ArchiveUploadInitResponse,
    ArchiveUploadVerifyRequest,
    append_archive_upload_chunk,
    archive_upload_headers,
    cancel_archive_upload,
    init_archive_upload,
    submit_archive_hash,
    submit_archive_publication,
)
from ..background_tasks import TaskType, get_task_manager
from ..background_tasks.api_models import TaskAccepted
from ..config import get_settings
from ..dependencies import get_current_user
from ..files import (
    CreateFileRequest,
    FileListResponse,
    RenameFileRequest,
    get_file_items,
)
from ..files.paths import resolve_file_path
from ..minecraft import get_docker_mc_manager

router = APIRouter(
    prefix="/archive",
    tags=["archive"],
)


async def _get_archive_base_path() -> Path:
    """Get the base path for archive files."""
    settings = get_settings()
    # Ensure archive directory exists
    await aioos.makedirs(settings.archive_path, exist_ok=True)
    return settings.archive_path


# Archive file management endpoints
@router.get("", response_model=FileListResponse)
async def list_archive_files(
    path: str = "/", _: UserPublic = Depends(get_current_user)
):
    """List files and directories in the archive"""
    base_path = await _get_archive_base_path()
    items = [item for item in await get_file_items(base_path, path) if not is_archive_stage(item.name)]

    return FileListResponse(items=items, current_path=path)


@router.get("/download")
async def download_archive_file(path: str, _: UserPublic = Depends(get_current_user)):
    """Download a specific archive file"""
    base_path = await _get_archive_base_path()
    file_path = await resolve_file_path(base_path, path)

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


@router.post("/upload/init", response_model=ArchiveUploadInitResponse)
async def init_archive_upload_endpoint(
    request: ArchiveUploadInitRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Start a resumable archive upload."""
    base_path = await _get_archive_base_path()
    return await init_archive_upload(base_path, request)


@router.head("/upload/{upload_id}")
async def get_archive_upload_status(
    upload_id: str,
    _: UserPublic = Depends(get_current_user),
) -> Response:
    """Return the server-side offset for a resumable upload."""
    headers = await archive_upload_headers(upload_id)
    return Response(status_code=204, headers=headers)


@router.patch("/upload/{upload_id}", response_model=ArchiveUploadChunkResponse)
async def upload_archive_chunk(
    upload_id: str,
    request: Request,
    upload_offset: int = Header(..., alias="Upload-Offset"),
    _: UserPublic = Depends(get_current_user),
):
    """Append one chunk to a resumable archive upload."""
    body = await request.body()
    return await append_archive_upload_chunk(upload_id, upload_offset, body)


@router.delete("/upload/{upload_id}", status_code=204)
async def cancel_archive_upload_endpoint(
    upload_id: str,
    _: UserPublic = Depends(get_current_user),
) -> None:
    """Cancel a resumable archive upload and remove its temporary file."""
    await cancel_archive_upload(upload_id)


@router.post("/upload/{upload_id}/sha256", response_model=TaskAccepted, status_code=202)
async def hash_archive_upload(upload_id: str, user: UserPublic = Depends(get_current_user)) -> TaskAccepted:
    return await submit_archive_hash(upload_id, user.id)


@router.post("/upload/{upload_id}/verify", response_model=TaskAccepted, status_code=202)
async def verify_archive_upload_endpoint(
    upload_id: str, request: ArchiveUploadVerifyRequest,
    user: UserPublic = Depends(get_current_user),
) -> TaskAccepted:
    return await submit_archive_publication(upload_id, request, user.id)


@router.post("/create")
async def create_archive_file_or_directory(
    create_request: CreateFileRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Create a new file or directory in the archive"""
    base_path = await _get_archive_base_path()
    message = await ArchiveApplication(base_path, _.id).create(create_request)

    return {"message": message}


@router.delete("", response_model=TaskAccepted, status_code=202)
async def delete_archive_file_or_directory(
    path: str, _: UserPublic = Depends(get_current_user)
):
    """Delete an archive file or directory"""
    base_path = await _get_archive_base_path()
    return await ArchiveApplication(base_path, _.id).submit_delete(path)


@router.post("/rename")
async def rename_archive_file_or_directory(
    rename_request: RenameFileRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Rename an archive file or directory"""
    base_path = await _get_archive_base_path()
    message = await ArchiveApplication(base_path, _.id).rename(rename_request)

    return {"message": message}


@router.post("/compress", response_model=CreateArchiveResponse)
async def create_server_archive_endpoint(
    request: CreateArchiveRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Create a compressed archive from server files as a background task."""
    instance = get_docker_mc_manager().get_instance(request.server_id)

    if not await instance.exists():
        raise HTTPException(
            status_code=404, detail=f"Server '{request.server_id}' not found"
        )

    if request.path is not None:
        if not request.path.startswith("/"):
            request.path = "/" + request.path

        data_dir = instance.get_data_path()
        if request.path != "/":
            target_path = await resolve_file_path(data_dir, request.path)
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

    plan = await prepare_compression(instance, request.path)
    result = await get_task_manager().submit_durable(
        task_type=TaskType.ARCHIVE_CREATE,
        name=task_name,
        task_generator=compress(plan),
        claims=plan.claims,
        server_id=request.server_id,
        cancellable=True,
        actor_id=_.id,
    )

    return CreateArchiveResponse(task_id=result.task_id)
