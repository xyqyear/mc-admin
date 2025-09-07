"""
Archive file management endpoints.
Provides CRUD operations for archive files using the configured archive directory.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..common.file_operations import (
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
from ..config import settings
from ..dependencies import get_current_user
from ..minecraft.utils import exec_command
from ..models import UserPublic

router = APIRouter(
    prefix="/archive",
    tags=["archive"],
)


class SHA256Response(BaseModel):
    sha256: str
    filename: str


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
    try:
        base_path = _get_archive_base_path()
        items = await get_file_items(base_path, path)

        return FileListResponse(items=items, current_path=path)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list archive files: {str(e)}")


@router.get("/content")
async def get_archive_file_content(
    path: str, _: UserPublic = Depends(get_current_user)
):
    """Get content of a specific archive file"""
    try:
        base_path = _get_archive_base_path()
        content = await get_file_content(base_path, path)

        return FileContent(content=content)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read archive file: {str(e)}")


@router.post("/content")
async def update_archive_file_content(
    path: str,
    file_content: FileContent,
    _: UserPublic = Depends(get_current_user),
):
    """Update content of a specific archive file"""
    try:
        base_path = _get_archive_base_path()
        await update_file_content(base_path, path, file_content.content)

        return {"message": "Archive file updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update archive file: {str(e)}")


@router.get("/download")
async def download_archive_file(
    path: str, _: UserPublic = Depends(get_current_user)
):
    """Download a specific archive file"""
    try:
        base_path = _get_archive_base_path()
        file_path = base_path / path.lstrip("/")

        # Validate file exists and is a file (not a directory)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Archive file not found")

        if not file_path.is_file():
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
            status_code=500, detail=f"Failed to download archive file: {str(e)}"
        )


@router.post("/upload")
async def upload_archive_file(
    path: str = "/",
    file: UploadFile = File(...),
    allow_overwrite: bool = False,
    _: UserPublic = Depends(get_current_user),
):
    """Upload a file to the archive"""
    try:
        base_path = _get_archive_base_path()
        filename = await upload_file(base_path, path, file, allow_overwrite=allow_overwrite)

        return {"message": f"Archive file '{filename}' uploaded successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload archive file: {str(e)}")


@router.post("/create")
async def create_archive_file_or_directory(
    create_request: CreateFileRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Create a new file or directory in the archive"""
    try:
        base_path = _get_archive_base_path()
        message = await create_file_or_directory(base_path, create_request)

        return {"message": message}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create archive {'directory' if create_request.type == 'directory' else 'file'}: {str(e)}",
        )


@router.delete("")
async def delete_archive_file_or_directory(
    path: str, _: UserPublic = Depends(get_current_user)
):
    """Delete an archive file or directory"""
    try:
        base_path = _get_archive_base_path()
        message = await delete_file_or_directory(base_path, path)

        return {"message": message}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete archive item: {str(e)}")


@router.post("/rename")
async def rename_archive_file_or_directory(
    rename_request: RenameFileRequest,
    _: UserPublic = Depends(get_current_user),
):
    """Rename an archive file or directory"""
    try:
        base_path = _get_archive_base_path()
        message = await rename_file_or_directory(base_path, rename_request)

        return {"message": message}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rename archive item: {str(e)}")


@router.get("/sha256", response_model=SHA256Response)
async def get_archive_file_sha256(
    path: str, _: UserPublic = Depends(get_current_user)
):
    """Calculate SHA256 hash of a specific archive file"""
    try:
        base_path = _get_archive_base_path()
        file_path = base_path / path.lstrip("/")

        # Validate file exists and is a file (not a directory)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Archive file not found")

        if not file_path.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")

        # Execute sha256sum command
        output = await exec_command("sha256sum", str(file_path))
        
        # Parse output: "{hash} {file}" format, split by space and take first part
        parts = output.strip().split()
        if len(parts) < 1:
            raise HTTPException(status_code=500, detail="Invalid sha256sum output")
        
        sha256_hash = parts[0]
        
        return SHA256Response(
            sha256=sha256_hash,
            filename=file_path.name
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to calculate SHA256 hash: {str(e)}"
        )