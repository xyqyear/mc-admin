"""
Utility functions for file operations including session management and async helpers.
"""

import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

from aiofiles import os as aioos
from asyncer import asyncify

from .types import UploadSession

# Global upload session storage
_upload_sessions: Dict[str, UploadSession] = {}
_SESSION_TIMEOUT = 3600  # 1 hour timeout


def _cleanup_expired_sessions():
    """Remove expired upload sessions"""
    current_time = time.time()
    expired_sessions = [
        session_id
        for session_id, session in _upload_sessions.items()
        if session.expires_at < current_time
    ]
    for session_id in expired_sessions:
        del _upload_sessions[session_id]


def _create_session_id() -> str:
    """Generate a unique session ID"""
    return str(uuid.uuid4())


def get_upload_session(session_id: str) -> Optional[UploadSession]:
    """Get upload session by ID"""
    _cleanup_expired_sessions()
    return _upload_sessions.get(session_id)


def set_upload_session(session_id: str, session: UploadSession):
    """Store upload session"""
    _cleanup_expired_sessions()
    _upload_sessions[session_id] = session


def remove_upload_session(session_id: str) -> bool:
    """Remove upload session, returns True if existed"""
    _cleanup_expired_sessions()
    return _upload_sessions.pop(session_id, None) is not None


def create_upload_session(conflicts, reusable: bool = False) -> str:
    """Create new upload session with conflicts"""
    session_id = _create_session_id()
    current_time = time.time()

    session = UploadSession(
        session_id=session_id,
        conflicts=conflicts,
        expires_at=current_time + _SESSION_TIMEOUT,
        created_at=current_time,
        reusable=reusable,
    )

    set_upload_session(session_id, session)
    return session_id


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


async def get_uid_gid(path: Path) -> tuple[int, int]:
    """Get the UID and GID of the specified path."""
    stat_info = await aioos.stat(path)
    return stat_info.st_uid, stat_info.st_gid


async def set_file_ownership(file_path: Path, base_path: Path) -> None:
    """Set file ownership to match base directory ownership"""
    uid, gid = await get_uid_gid(base_path)
    await _chown_async(file_path, uid, gid)
