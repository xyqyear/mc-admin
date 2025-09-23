"""
Common file operations utilities for both server files and archive files.
This module provides reusable functions for file management operations.
"""

import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Dict, List, Literal, Optional

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


# Multi-file upload models
class FileStructureItem(BaseModel):
    """Represents a file or directory in the upload structure"""
    path: str  # Relative path within the upload structure
    name: str  # File or directory name
    type: Literal["file", "directory"]
    size: Optional[int] = None  # Size for files, None for directories


class MultiFileUploadRequest(BaseModel):
    """Request to check file structure before upload"""
    files: List[FileStructureItem]  # Files and directories to upload


class OverwriteConflict(BaseModel):
    """Information about a file that would be overwritten"""
    path: str  # Full path on server
    type: Literal["file", "directory"]
    current_size: Optional[int] = None  # Current file size if it's a file
    new_size: Optional[int] = None  # New file size if it's a file


class UploadConflictResponse(BaseModel):
    """Response with overwrite conflicts"""
    session_id: str  # Unique session ID for this upload
    conflicts: List[OverwriteConflict]  # Files that would be overwritten


class OverwriteDecision(BaseModel):
    """Overwrite decision for a specific file"""
    path: str
    overwrite: bool


class OverwritePolicy(BaseModel):
    """Policy for handling overwrite conflicts"""
    mode: Literal["always_overwrite", "never_overwrite", "per_file"]
    decisions: Optional[List[OverwriteDecision]] = None  # Required when mode is "per_file"


class UploadSession(BaseModel):
    """Upload session data stored in memory"""
    session_id: str
    conflicts: List[OverwriteConflict]
    policy: Optional[OverwritePolicy] = None
    expires_at: float  # Unix timestamp
    created_at: float  # Unix timestamp
    reusable: bool = False  # Whether session can be reused for multiple uploads


# Upload result models
class UploadFileResult(BaseModel):
    """Result for individual file upload"""
    status: Literal["success", "failed", "skipped"]
    reason: Optional[str] = None  # Error message for failed, reason for skipped ("exists", "no_decision")


class MultiFileUploadResult(BaseModel):
    """Results for multi-file upload operation"""
    message: str
    results: Dict[str, UploadFileResult]  # Key is file path, value is result


# Global upload session storage
_upload_sessions: Dict[str, UploadSession] = {}
_SESSION_TIMEOUT = 3600  # 1 hour timeout


def _cleanup_expired_sessions():
    """Remove expired upload sessions"""
    current_time = time.time()
    expired_sessions = [
        session_id for session_id, session in _upload_sessions.items()
        if session.expires_at < current_time
    ]
    for session_id in expired_sessions:
        del _upload_sessions[session_id]


def _create_session_id() -> str:
    """Generate a unique session ID"""
    return str(uuid.uuid4())


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


# Multi-file upload functions
async def check_upload_conflicts(
    base_path: Path, upload_path: str, upload_request: MultiFileUploadRequest
) -> UploadConflictResponse:
    """Check for conflicts before multi-file upload"""
    _cleanup_expired_sessions()

    conflicts = []
    target_base = base_path / upload_path.lstrip("/")

    for file_item in upload_request.files:
        if file_item.type == "file":
            target_path = target_base / file_item.path.lstrip("/")
            if await aioos.path.exists(target_path):
                current_size = None
                if await aioos.path.isfile(target_path):
                    stat_result = await aioos.stat(target_path)
                    current_size = stat_result.st_size

                # Use file path relative to upload path
                # This will match the file_relative_path used in upload_multiple_files
                relative_conflict_path = file_item.path.lstrip("/")

                conflicts.append(OverwriteConflict(
                    path=relative_conflict_path,
                    type="file",
                    current_size=current_size,
                    new_size=file_item.size
                ))

    # Create upload session
    session_id = _create_session_id()
    current_time = time.time()

    session = UploadSession(
        session_id=session_id,
        conflicts=conflicts,
        expires_at=current_time + _SESSION_TIMEOUT,
        created_at=current_time
    )

    _upload_sessions[session_id] = session

    return UploadConflictResponse(
        session_id=session_id,
        conflicts=conflicts
    )


async def set_upload_policy(session_id: str, policy: OverwritePolicy, reusable: bool = False) -> None:
    """Set the overwrite policy for an upload session"""
    _cleanup_expired_sessions()

    if session_id not in _upload_sessions:
        raise HTTPException(status_code=404, detail="Upload session not found or expired")

    session = _upload_sessions[session_id]

    # Validate per-file decisions if required
    if policy.mode == "per_file":
        if not policy.decisions:
            raise HTTPException(status_code=400, detail="Decisions required for per_file mode")

        conflict_paths = {conflict.path for conflict in session.conflicts}
        decision_paths = {decision.path for decision in policy.decisions}

        if conflict_paths != decision_paths:
            raise HTTPException(
                status_code=400,
                detail="Decisions must be provided for all conflicting files"
            )

    session.policy = policy
    session.reusable = reusable
    _upload_sessions[session_id] = session


async def upload_multiple_files(
    base_path: Path,
    session_id: str,
    upload_path: str,
    files: List[UploadFile]
) -> MultiFileUploadResult:
    """Upload multiple files using the prepared session"""
    _cleanup_expired_sessions()

    if session_id not in _upload_sessions:
        raise HTTPException(status_code=404, detail="Upload session not found or expired")

    session = _upload_sessions[session_id]

    if not session.policy:
        raise HTTPException(status_code=400, detail="Upload policy not set")

    # Create a copy of session data to prevent concurrent modification
    session_copy = session.model_copy()

    # Only remove session if it's not reusable
    if not session.reusable:
        del _upload_sessions[session_id]

    target_base = base_path / upload_path.lstrip("/")

    # Process upload policy - build overwrite decisions map
    overwrite_decisions = {}
    policy = session_copy.policy
    if policy and policy.mode == "always_overwrite":
        for conflict in session_copy.conflicts:
            overwrite_decisions[conflict.path] = True
    elif policy and policy.mode == "never_overwrite":
        for conflict in session_copy.conflicts:
            overwrite_decisions[conflict.path] = False
    elif policy and policy.mode == "per_file":
        for decision in policy.decisions or []:
            overwrite_decisions[decision.path] = decision.overwrite

    results: Dict[str, UploadFileResult] = {}

    try:
        # Process each uploaded file directly
        for file in files:
            if not file.filename:
                continue

            # file.filename contains the complete relative path (e.g., "config/settings.yml")
            file_relative_path = file.filename.lstrip("/")
            target_path = target_base / file_relative_path

            # Use file relative path as the key instead of just filename
            result_key = file_relative_path

            # Ensure parent directory exists
            parent_dir = target_path.parent
            if not await aioos.path.exists(parent_dir):
                await aioos.makedirs(parent_dir, exist_ok=True)

                # Set ownership for created directory
                uid, gid = await get_uid_gid(base_path)
                if uid is not None and gid is not None:
                    try:
                        await _chown_async(parent_dir, uid, gid)
                    except (OSError, PermissionError):
                        pass

            # Check if file exists and handle overwrite logic
            if await aioos.path.exists(target_path):
                if file_relative_path in overwrite_decisions:
                    if not overwrite_decisions[file_relative_path]:
                        results[result_key] = UploadFileResult(
                            status="skipped",
                            reason="exists"
                        )
                        continue
                elif policy:
                    if policy.mode == "always_overwrite":
                        pass  # Overwrite
                    elif policy.mode == "never_overwrite":
                        results[result_key] = UploadFileResult(
                            status="skipped",
                            reason="exists"
                        )
                        continue
                    else:
                        results[result_key] = UploadFileResult(
                            status="skipped",
                            reason="no_decision"
                        )
                        continue

            try:
                # Upload file
                async with aiofiles.open(target_path, "wb") as f:
                    await file.seek(0)  # Reset file position
                    while chunk := await file.read(10 * 1024 * 1024):
                        await f.write(chunk)

                # Set ownership for uploaded file
                uid, gid = await get_uid_gid(base_path)
                if uid is not None and gid is not None:
                    try:
                        await _chown_async(target_path, uid, gid)
                    except (OSError, PermissionError):
                        pass

                results[result_key] = UploadFileResult(
                    status="success"
                )

            except Exception as file_error:
                results[result_key] = UploadFileResult(
                    status="failed",
                    reason=str(file_error)
                )


    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    # Count successful uploads
    success_count = sum(1 for result in results.values() if result.status == "success")
    total_count = len(results)

    return MultiFileUploadResult(
        message=f"Upload completed. Success: {success_count}/{total_count}",
        results=results
    )


def get_upload_session(session_id: str) -> Optional[UploadSession]:
    """Get upload session by ID"""
    _cleanup_expired_sessions()
    return _upload_sessions.get(session_id)
