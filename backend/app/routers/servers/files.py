import shutil
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ...config import settings
from ...dependencies import get_current_user
from ...minecraft import DockerMCManager

router = APIRouter(
    prefix="/servers",
    tags=["files"],
)

# Initialize the Docker MC Manager
mc_manager = DockerMCManager(settings.server_path)


# Pydantic models for file operations
class FileItem(BaseModel):
    name: str
    type: str  # 'file' or 'directory'
    size: int
    modified_at: str
    path: str


class FileListResponse(BaseModel):
    items: List[FileItem]
    current_path: str


class FileContent(BaseModel):
    content: str


class CreateFileRequest(BaseModel):
    name: str
    type: str  # 'file' or 'directory'
    path: str


class RenameFileRequest(BaseModel):
    old_path: str
    new_name: str


# Helper functions for file management
def _get_server_data_path(instance) -> Path:
    """Get the data path for the server instance."""
    return instance.get_project_path() / "data"


def _get_file_items(base_path: Path, current_path: str = "/") -> List[FileItem]:
    """Get list of files and directories in the specified path."""
    if current_path.startswith("/"):
        current_path = current_path[1:]  # Remove leading slash

    actual_path = base_path / current_path if current_path else base_path

    if not actual_path.exists() or not actual_path.is_dir():
        return []

    items = []

    try:
        for item in actual_path.iterdir():
            relative_path = item.relative_to(base_path)
            file_path = "/" + str(relative_path).replace("\\", "/")

            if item.is_file():
                size = item.stat().st_size
                file_type = "file"
            else:
                size = 0
                file_type = "directory"

            modified_at = item.stat().st_mtime
            modified_at_str = f"{modified_at:.0f}"  # Unix timestamp as string

            items.append(
                FileItem(
                    name=item.name,
                    type=file_type,
                    size=size,
                    modified_at=modified_at_str,
                    path=file_path,
                )
            )
    except PermissionError:
        # Handle permission errors gracefully
        pass

    # Sort items: directories first, then files, both alphabetically
    items.sort(key=lambda x: (x.type == "file", x.name.lower()))

    return items


# File management endpoints
@router.get("/{server_id}/files", response_model=FileListResponse)
async def list_files(
    server_id: str, path: str = "/", _: str = Depends(get_current_user)
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
        items = _get_file_items(base_path, path)

        return FileListResponse(items=items, current_path=path)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")


@router.get("/{server_id}/files/content")
async def get_file_content(
    server_id: str, path: str, _: str = Depends(get_current_user)
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

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        if not file_path.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, "r", encoding="latin1") as f:
                    content = f.read()
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
    _: str = Depends(get_current_user),
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

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        if not file_path.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")

        # Create backup
        backup_path = file_path.with_suffix(file_path.suffix + ".backup")
        shutil.copy2(file_path, backup_path)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(file_content.content)
        except Exception as e:
            # Restore from backup if write fails
            if backup_path.exists():
                shutil.copy2(backup_path, file_path)
            raise e
        finally:
            # Clean up backup
            if backup_path.exists():
                backup_path.unlink()

        return {"message": "File updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update file: {str(e)}")


@router.get("/{server_id}/files/download")
async def download_file(server_id: str, path: str, _: str = Depends(get_current_user)):
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

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

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
            status_code=500, detail=f"Failed to download file: {str(e)}"
        )


@router.post("/{server_id}/files/upload")
async def upload_file(
    server_id: str,
    path: str = "/",
    file: UploadFile = File(...),
    _: str = Depends(get_current_user),
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
        target_dir.mkdir(parents=True, exist_ok=True)

        if not target_dir.is_dir():
            raise HTTPException(
                status_code=400, detail="Target path is not a directory"
            )

        file_path = target_dir / (file.filename or "unnamed_file")

        # Check if file already exists
        if file_path.exists():
            raise HTTPException(status_code=409, detail="File already exists")

        # Write file
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        return {"message": f"File '{file.filename}' uploaded successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")


@router.post("/{server_id}/files/create")
async def create_file_or_directory(
    server_id: str,
    create_request: CreateFileRequest,
    _: str = Depends(get_current_user),
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
        if target_path.exists():
            raise HTTPException(
                status_code=409,
                detail=f"{'Directory' if create_request.type == 'directory' else 'File'} already exists",
            )

        # Create parent directories if needed
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if create_request.type == "directory":
            target_path.mkdir()
            message = f"Directory '{create_request.name}' created successfully"
        elif create_request.type == "file":
            target_path.touch()
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
    server_id: str, path: str, _: str = Depends(get_current_user)
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

        if not target_path.exists():
            raise HTTPException(status_code=404, detail="File or directory not found")

        if target_path.is_file():
            target_path.unlink()
            message = f"File '{target_path.name}' deleted successfully"
        elif target_path.is_dir():
            shutil.rmtree(target_path)
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
    _: str = Depends(get_current_user),
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

        if not old_path.exists():
            raise HTTPException(status_code=404, detail="File or directory not found")

        if new_path.exists():
            raise HTTPException(status_code=409, detail="Target name already exists")

        old_path.rename(new_path)

        item_type = "Directory" if new_path.is_dir() else "File"
        return {"message": f"{item_type} renamed successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rename: {str(e)}")