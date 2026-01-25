"""
Multi-file upload operations with conflict detection and session management.
"""

from pathlib import Path
from typing import Dict, List

import aiofiles
from aiofiles import os as aioos
from fastapi import HTTPException, UploadFile

from .types import (
    MultiFileUploadRequest,
    MultiFileUploadResult,
    OverwriteConflict,
    OverwritePolicy,
    UploadConflictResponse,
    UploadFileResult,
)
from .utils import (
    create_upload_session,
    get_upload_session,
    makedirs_with_ownership,
    remove_upload_session,
    set_file_ownership,
    set_upload_session,
)


async def check_upload_conflicts(
    base_path: Path, upload_path: str, upload_request: MultiFileUploadRequest
) -> UploadConflictResponse:
    """Check for conflicts before multi-file upload"""
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

                conflicts.append(
                    OverwriteConflict(
                        path=relative_conflict_path,
                        type="file",
                        current_size=current_size,
                        new_size=file_item.size,
                    )
                )

    # Create upload session
    session_id = create_upload_session(conflicts, reusable=False)

    return UploadConflictResponse(session_id=session_id, conflicts=conflicts)


async def set_upload_policy(
    session_id: str, policy: OverwritePolicy, reusable: bool = False
) -> None:
    """Set the overwrite policy for an upload session"""
    session = get_upload_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404, detail="Upload session not found or expired"
        )

    # Validate per-file decisions if required
    if policy.mode == "per_file":
        if not policy.decisions:
            raise HTTPException(
                status_code=400, detail="Decisions required for per_file mode"
            )

        conflict_paths = {conflict.path for conflict in session.conflicts}
        decision_paths = {decision.path for decision in policy.decisions}

        if conflict_paths != decision_paths:
            raise HTTPException(
                status_code=400,
                detail="Decisions must be provided for all conflicting files",
            )

    session.policy = policy
    session.reusable = reusable
    set_upload_session(session_id, session)


async def upload_multiple_files(
    base_path: Path, session_id: str, upload_path: str, files: List[UploadFile]
) -> MultiFileUploadResult:
    """Upload multiple files using the prepared session"""
    session = get_upload_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404, detail="Upload session not found or expired"
        )

    if not session.policy:
        raise HTTPException(status_code=400, detail="Upload policy not set")

    # Create a copy of session data to prevent concurrent modification
    session_copy = session.model_copy()

    # Only remove session if it's not reusable
    if not session.reusable:
        remove_upload_session(session_id)

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
                # Create all intermediate directories with proper ownership
                await makedirs_with_ownership(parent_dir, base_path)

            # Check if file exists and handle overwrite logic
            if await aioos.path.exists(target_path):
                if file_relative_path in overwrite_decisions:
                    if not overwrite_decisions[file_relative_path]:
                        results[result_key] = UploadFileResult(
                            status="skipped", reason="exists"
                        )
                        continue
                elif policy:
                    if policy.mode == "always_overwrite":
                        pass  # Overwrite
                    elif policy.mode == "never_overwrite":
                        results[result_key] = UploadFileResult(
                            status="skipped", reason="exists"
                        )
                        continue
                    else:
                        results[result_key] = UploadFileResult(
                            status="skipped", reason="no_decision"
                        )
                        continue

            try:
                # Upload file
                async with aiofiles.open(target_path, "wb") as f:
                    await file.seek(0)  # Reset file position
                    while chunk := await file.read(10 * 1024 * 1024):
                        await f.write(chunk)

                # Set ownership for uploaded file
                await set_file_ownership(target_path, base_path)

                results[result_key] = UploadFileResult(status="success")

            except Exception as file_error:
                results[result_key] = UploadFileResult(
                    status="failed", reason=str(file_error)
                )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    # Count successful uploads
    success_count = sum(1 for result in results.values() if result.status == "success")
    total_count = len(results)

    return MultiFileUploadResult(
        message=f"Upload completed. Success: {success_count}/{total_count}",
        results=results,
    )
