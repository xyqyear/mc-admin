from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator, Literal

import aiofiles
from aiofiles import os as aioos
from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..files.utils import makedirs_with_ownership, set_file_ownership
from ..utils import async_fs

ARCHIVE_UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024
ARCHIVE_UPLOAD_TTL_SECONDS = 60 * 60
ARCHIVE_UPLOAD_TMP_DIR = Path("/tmp/mc-admin-archive-uploads")
ArchiveUploadState = Literal["receiving", "uploaded", "hashed"]


class ArchiveUploadInitRequest(BaseModel):
    path: str = "/"
    filename: str
    size: int = Field(gt=0)
    allow_overwrite: bool = False


class ArchiveUploadInitResponse(BaseModel):
    upload_id: str
    offset: int
    chunk_size: int
    expires_at: float


class ArchiveUploadChunkResponse(BaseModel):
    upload_id: str
    offset: int
    complete: bool
    pending_verification: bool = False
    path: str | None = None
    filename: str | None = None


class ArchiveUploadVerifyRequest(BaseModel):
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class ArchiveUploadVerifyResponse(BaseModel):
    upload_id: str
    path: str
    filename: str
    sha256: str


class ArchiveSHA256Event(BaseModel):
    event_type: Literal["start", "progress", "complete", "error"]
    loaded: int | None = None
    total: int | None = None
    percent: float | None = None
    sha256: str | None = None
    filename: str | None = None
    message: str | None = None


@dataclass
class ArchiveUploadSession:
    upload_id: str
    temp_path: Path
    base_path: Path
    target_dir: Path
    target_path: Path
    archive_path: str
    filename: str
    size: int
    allow_overwrite: bool
    created_at: float
    expires_at: float
    state: ArchiveUploadState = "receiving"
    server_sha256: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_archive_upload_sessions: dict[str, ArchiveUploadSession] = {}
_archive_upload_sessions_lock = asyncio.Lock()


def _now() -> float:
    return time.time()


def _new_expiry() -> float:
    return _now() + ARCHIVE_UPLOAD_TTL_SECONDS


def _normalize_archive_dir(path: str) -> str:
    clean = path.strip()
    if not clean or clean == "/":
        return "/"
    return "/" + clean.strip("/")


def _archive_path_for(directory: str, filename: str) -> str:
    return f"/{filename}" if directory == "/" else f"{directory}/{filename}"


def _validate_filename(filename: str) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    if filename in {".", ".."} or Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return filename


async def _resolve_under_base(base_path: Path, path: str) -> Path:
    base = await async_fs.resolve(base_path)
    candidate = await async_fs.resolve(base / path.lstrip("/"), strict=False)
    try:
        candidate.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="Path escapes archive directory")
    return candidate


async def _cleanup_expired_sessions_locked() -> None:
    now = _now()
    expired = [
        upload_id
        for upload_id, session in _archive_upload_sessions.items()
        if session.expires_at < now
    ]
    for upload_id in expired:
        session = _archive_upload_sessions.pop(upload_id)
        await _delete_upload_temp(session)


async def _get_session(upload_id: str) -> ArchiveUploadSession:
    async with _archive_upload_sessions_lock:
        await _cleanup_expired_sessions_locked()
        session = _archive_upload_sessions.get(upload_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Upload session not found")
    return session


async def _session_offset(session: ArchiveUploadSession) -> int:
    try:
        return (await aioos.stat(session.temp_path)).st_size
    except FileNotFoundError:
        return 0


async def _delete_upload_temp(session: ArchiveUploadSession) -> None:
    try:
        await aioos.unlink(session.temp_path)
    except FileNotFoundError:
        pass


async def init_archive_upload(
    base_path: Path, request: ArchiveUploadInitRequest
) -> ArchiveUploadInitResponse:
    filename = _validate_filename(request.filename)
    directory = _normalize_archive_dir(request.path)
    target_dir = await _resolve_under_base(base_path, directory)

    if await aioos.path.exists(target_dir) and not await aioos.path.isdir(target_dir):
        raise HTTPException(status_code=400, detail="Target path is not a directory")

    target_path = target_dir / filename
    resolved_target = await async_fs.resolve(target_path, strict=False)
    try:
        resolved_target.relative_to(await async_fs.resolve(base_path))
    except ValueError:
        raise HTTPException(status_code=400, detail="Path escapes archive directory")

    if await aioos.path.isdir(target_path):
        raise HTTPException(status_code=409, detail="Target path is a directory")
    if not request.allow_overwrite and await aioos.path.exists(target_path):
        raise HTTPException(status_code=409, detail="File already exists")

    await aioos.makedirs(ARCHIVE_UPLOAD_TMP_DIR, exist_ok=True)
    upload_id = str(uuid.uuid4())
    temp_path = ARCHIVE_UPLOAD_TMP_DIR / f"{upload_id}.part"
    async with aiofiles.open(temp_path, "wb"):
        pass

    now = _now()
    session = ArchiveUploadSession(
        upload_id=upload_id,
        temp_path=temp_path,
        base_path=base_path,
        target_dir=target_dir,
        target_path=target_path,
        archive_path=_archive_path_for(directory, filename),
        filename=filename,
        size=request.size,
        allow_overwrite=request.allow_overwrite,
        created_at=now,
        expires_at=now + ARCHIVE_UPLOAD_TTL_SECONDS,
    )

    async with _archive_upload_sessions_lock:
        await _cleanup_expired_sessions_locked()
        _archive_upload_sessions[upload_id] = session

    return ArchiveUploadInitResponse(
        upload_id=upload_id,
        offset=0,
        chunk_size=ARCHIVE_UPLOAD_CHUNK_SIZE,
        expires_at=session.expires_at,
    )


async def archive_upload_headers(upload_id: str) -> dict[str, str]:
    session = await _get_session(upload_id)
    async with session.lock:
        offset = await _session_offset(session)
        return {
            "Upload-Offset": str(offset),
            "Upload-Length": str(session.size),
            "Upload-Chunk-Size": str(ARCHIVE_UPLOAD_CHUNK_SIZE),
            "Upload-Expires": str(int(session.expires_at)),
            "Upload-State": session.state,
        }


async def _publish_archive_upload(session: ArchiveUploadSession) -> None:
    if await aioos.path.exists(session.target_dir):
        if not await aioos.path.isdir(session.target_dir):
            raise HTTPException(status_code=400, detail="Target path is not a directory")
    else:
        await makedirs_with_ownership(session.target_dir, session.base_path)

    if await aioos.path.isdir(session.target_path):
        raise HTTPException(status_code=409, detail="Target path is a directory")
    if not session.allow_overwrite and await aioos.path.exists(session.target_path):
        raise HTTPException(status_code=409, detail="File already exists")

    staging_path = session.target_dir / f".{session.filename}.{session.upload_id}.uploading"
    try:
        try:
            await aioos.unlink(staging_path)
        except FileNotFoundError:
            pass
        await async_fs.copy2(session.temp_path, staging_path)
        staged_size = (await aioos.stat(staging_path)).st_size
        if staged_size != session.size:
            raise HTTPException(status_code=500, detail="Finalized file size mismatch")
        await aioos.replace(staging_path, session.target_path)
        await set_file_ownership(session.target_path, session.base_path)
        await _delete_upload_temp(session)
    except Exception:
        try:
            await aioos.unlink(staging_path)
        except FileNotFoundError:
            pass
        raise


async def append_archive_upload_chunk(
    upload_id: str, upload_offset: int, body: bytes
) -> ArchiveUploadChunkResponse:
    if len(body) > ARCHIVE_UPLOAD_CHUNK_SIZE:
        raise HTTPException(status_code=413, detail="Upload chunk is too large")

    session = await _get_session(upload_id)
    async with session.lock:
        if session.state != "receiving":
            offset = await _session_offset(session)
            return ArchiveUploadChunkResponse(
                upload_id=upload_id,
                offset=offset,
                complete=offset == session.size,
                pending_verification=offset == session.size,
                path=session.archive_path if offset == session.size else None,
                filename=session.filename if offset == session.size else None,
            )

        current_offset = await _session_offset(session)
        if upload_offset != current_offset:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Upload offset mismatch",
                    "offset": current_offset,
                },
            )
        if upload_offset + len(body) > session.size:
            raise HTTPException(status_code=400, detail="Upload exceeds declared size")
        if session.size > 0 and not body:
            raise HTTPException(status_code=400, detail="Upload chunk is empty")

        if body:
            async with aiofiles.open(session.temp_path, "ab") as f:
                await f.write(body)

        new_offset = upload_offset + len(body)
        session.expires_at = _new_expiry()
        complete = new_offset == session.size
        if complete:
            session.state = "uploaded"
            session.server_sha256 = None

    return ArchiveUploadChunkResponse(
        upload_id=upload_id,
        offset=new_offset,
        complete=complete,
        pending_verification=complete,
        path=session.archive_path if complete else None,
        filename=session.filename if complete else None,
    )


async def cancel_archive_upload(upload_id: str) -> None:
    async with _archive_upload_sessions_lock:
        await _cleanup_expired_sessions_locked()
        session = _archive_upload_sessions.pop(upload_id, None)
    if session is None:
        raise HTTPException(status_code=404, detail="Upload session not found")
    async with session.lock:
        await _delete_upload_temp(session)


async def ensure_archive_upload_ready_for_sha256(upload_id: str) -> None:
    session = await _get_session(upload_id)
    async with session.lock:
        offset = await _session_offset(session)
        if offset != session.size or session.state == "receiving":
            raise HTTPException(status_code=409, detail="Upload is not complete")
        session.expires_at = _new_expiry()


async def _iter_file_sha256_events(
    file_path: Path, filename: str
) -> AsyncGenerator[ArchiveSHA256Event, None]:
    total = (await aioos.stat(file_path)).st_size
    loaded = 0
    hasher = hashlib.sha256()
    yield ArchiveSHA256Event(
        event_type="start",
        loaded=0,
        total=total,
        percent=0,
        filename=filename,
    )
    async with aiofiles.open(file_path, "rb") as f:
        while True:
            chunk = await f.read(ARCHIVE_UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            await asyncio.to_thread(hasher.update, chunk)
            loaded += len(chunk)
            percent = (loaded / total * 100) if total else 100
            yield ArchiveSHA256Event(
                event_type="progress",
                loaded=loaded,
                total=total,
                percent=percent,
                filename=filename,
            )

    yield ArchiveSHA256Event(
        event_type="complete",
        loaded=loaded,
        total=total,
        percent=100,
        sha256=hasher.hexdigest(),
        filename=filename,
    )


async def iter_archive_upload_sha256_events(
    upload_id: str,
) -> AsyncGenerator[ArchiveSHA256Event, None]:
    session = await _get_session(upload_id)
    async with session.lock:
        offset = await _session_offset(session)
        if offset != session.size or session.state == "receiving":
            raise HTTPException(status_code=409, detail="Upload is not complete")

        async for event in _iter_file_sha256_events(
            session.temp_path, session.filename
        ):
            if event.event_type == "complete" and event.sha256:
                session.state = "hashed"
                session.server_sha256 = event.sha256
                session.expires_at = _new_expiry()
            yield event


async def verify_archive_upload(
    upload_id: str, request: ArchiveUploadVerifyRequest
) -> ArchiveUploadVerifyResponse:
    session = await _get_session(upload_id)
    async with session.lock:
        if session.state != "hashed" or not session.server_sha256:
            raise HTTPException(
                status_code=409, detail="Server SHA256 has not completed"
            )

        client_sha256 = request.sha256.lower()
        if client_sha256 != session.server_sha256:
            await _delete_upload_temp(session)
            async with _archive_upload_sessions_lock:
                _archive_upload_sessions.pop(upload_id, None)
            raise HTTPException(status_code=409, detail="SHA256 mismatch")

        await _publish_archive_upload(session)
        response = ArchiveUploadVerifyResponse(
            upload_id=upload_id,
            path=session.archive_path,
            filename=session.filename,
            sha256=session.server_sha256,
        )
        async with _archive_upload_sessions_lock:
            _archive_upload_sessions.pop(upload_id, None)
        return response
