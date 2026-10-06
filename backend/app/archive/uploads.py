from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import aclosing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import aiofiles
from aiofiles import os as aioos
from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..background_tasks import TaskProgress, TaskStatus, TaskType, get_task_manager
from ..background_tasks.api_models import TaskAccepted
from ..files.utils import makedirs_with_ownership, set_file_ownership
from ..operations.context import current_execution, retain_recovery_reference
from ..operations.coordinator import ConflictPolicy
from ..operations.finalization import finalize
from ..operations.journal_types import ResourceReference
from ..runtime_resources import current_runtime
from ..utils import async_fs

ARCHIVE_UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024
ARCHIVE_UPLOAD_TTL_SECONDS = 60 * 60
ARCHIVE_UPLOAD_TMP_DIR = Path("/tmp/mc-admin-archive-uploads")
ArchiveUploadState = Literal["receiving", "uploaded", "hashed", "published"]


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
    hash_task_id: str | None = None
    publish_task_id: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def get_archive_upload_sessions() -> dict[str, ArchiveUploadSession]:
    return current_runtime().archive_upload_sessions
def get_archive_upload_lock() -> asyncio.Lock:
    return current_runtime().archive_upload_lock


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
        for upload_id, session in get_archive_upload_sessions().items()
        if session.expires_at < now and not session.lock.locked()
        and not any(task_id and (task := get_task_manager().get_task(task_id)) is not None
                    and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
                    for task_id in (session.hash_task_id, session.publish_task_id))
    ]
    for upload_id in expired:
        session = get_archive_upload_sessions().pop(upload_id)
        await _delete_upload_temp(session)


async def _get_session(upload_id: str) -> ArchiveUploadSession:
    async with get_archive_upload_lock():
        await _cleanup_expired_sessions_locked()
        session = get_archive_upload_sessions().get(upload_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Upload session not found")
    return session


async def _session_offset(session: ArchiveUploadSession) -> int:
    if session.state == "published":
        return session.size
    try:
        return (await aioos.stat(session.temp_path)).st_size
    except FileNotFoundError:
        return 0


async def _delete_upload_temp(session: ArchiveUploadSession) -> None:
    try:
        await aioos.unlink(session.temp_path)
    except FileNotFoundError:
        pass


async def close_archive_uploads() -> None:
    async with get_archive_upload_lock():
        sessions = list(get_archive_upload_sessions().values())
        get_archive_upload_sessions().clear()
    for session in sessions:
        async with session.lock:
            await _delete_upload_temp(session)


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

    async with get_archive_upload_lock():
        await _cleanup_expired_sessions_locked()
        get_archive_upload_sessions()[upload_id] = session

    return ArchiveUploadInitResponse(
        upload_id=upload_id,
        offset=0,
        chunk_size=ARCHIVE_UPLOAD_CHUNK_SIZE,
        expires_at=session.expires_at,
    )


async def archive_upload_headers(upload_id: str) -> dict[str, str]:
    session = await _get_session(upload_id)
    offset = await _session_offset(session)
    return {
        "Upload-Offset": str(offset),
        "Upload-Length": str(session.size),
        "Upload-Chunk-Size": str(ARCHIVE_UPLOAD_CHUNK_SIZE),
        "Upload-Expires": str(int(session.expires_at)),
        "Upload-State": session.state,
        "Upload-Hash-Task": session.hash_task_id or "",
        "Upload-Publish-Task": session.publish_task_id or "",
    }


async def _publish_archive_upload(session: ArchiveUploadSession, *, actor_id: int | None = None) -> None:
    from .application import STAGE_PREFIX, mutate_archive

    token = session.upload_id.replace("-", "")
    stage = session.target_dir / f"{STAGE_PREFIX}{token}.tmp"

    async def publish() -> None:
        await retain_recovery_reference("archive_stage", token)
        try:
            await _publish_owned_upload(session)
        finally:
            try:
                await aioos.unlink(stage)
            except FileNotFoundError:
                pass
            execution = current_execution()
            if execution is not None:
                await execution.journal.resolve_reference(execution.operation_id, "archive_stage", token)

    await mutate_archive(
        session.base_path, [session.target_path, stage], publish,
        kind="archive_publish", actor_id=actor_id, policy=ConflictPolicy.WAIT,
    )


async def _publish_owned_upload(session: ArchiveUploadSession) -> None:
    if await aioos.path.exists(session.target_dir):
        if not await aioos.path.isdir(session.target_dir):
            raise HTTPException(status_code=400, detail="Target path is not a directory")
    else:
        await makedirs_with_ownership(session.target_dir, session.base_path)

    if await aioos.path.isdir(session.target_path):
        raise HTTPException(status_code=409, detail="Target path is a directory")
    if not session.allow_overwrite and await aioos.path.exists(session.target_path):
        raise HTTPException(status_code=409, detail="File already exists")

    from .application import STAGE_PREFIX

    staging_path = session.target_dir / f"{STAGE_PREFIX}{session.upload_id.replace('-', '')}.tmp"
    try:
        try:
            await aioos.unlink(staging_path)
        except FileNotFoundError:
            pass
        await async_fs.copy2(session.temp_path, staging_path)
        staged_size = (await aioos.stat(staging_path)).st_size
        if staged_size != session.size:
            raise HTTPException(status_code=500, detail="Finalized file size mismatch")
        await set_file_ownership(staging_path, session.base_path)
        if session.allow_overwrite:
            await aioos.replace(staging_path, session.target_path)
        else:
            try:
                await aioos.link(staging_path, session.target_path)
            except FileExistsError:
                raise HTTPException(status_code=409, detail="File already exists")
            await aioos.unlink(staging_path)
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

        new_offset = upload_offset + len(body)
        complete = new_offset == session.size

        async def append() -> None:
            if body:
                async with aiofiles.open(session.temp_path, "ab") as stream:
                    await stream.write(body)
            session.expires_at = _new_expiry()
            if complete:
                session.state = "uploaded"
                session.server_sha256 = None
        await finalize(append())

    return ArchiveUploadChunkResponse(
        upload_id=upload_id,
        offset=new_offset,
        complete=complete,
        pending_verification=complete,
        path=session.archive_path if complete else None,
        filename=session.filename if complete else None,
    )


async def cancel_archive_upload(upload_id: str) -> None:
    async with get_archive_upload_lock():
        await _cleanup_expired_sessions_locked()
        session = get_archive_upload_sessions().get(upload_id)
        if session and session.publish_task_id:
            task = get_task_manager().get_task(session.publish_task_id)
            if task and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                raise HTTPException(status_code=423, detail="文件正在发布，请等待任务完成")
        get_archive_upload_sessions().pop(upload_id, None)
    if session is None:
        raise HTTPException(status_code=404, detail="Upload session not found")
    for task_id in (session.hash_task_id, session.publish_task_id):
        if task_id:
            await get_task_manager().cancel(task_id)
            if future := get_task_manager().get_future(task_id):
                await finalize(asyncio.shield(future))
    async with session.lock:
        await _delete_upload_temp(session)


async def ensure_archive_upload_ready_for_sha256(upload_id: str) -> None:
    session = await _get_session(upload_id)
    async with session.lock:
        offset = await _session_offset(session)
        if offset != session.size or session.state == "receiving":
            raise HTTPException(status_code=409, detail="Upload is not complete")
        session.expires_at = _new_expiry()


async def submit_archive_hash(upload_id: str, actor_id: int) -> TaskAccepted:
    session = await _get_session(upload_id)
    if session.hash_task_id:
        task = get_task_manager().get_task(session.hash_task_id)
        if task is not None and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.COMPLETED):
            return TaskAccepted(task_id=task.task_id)
    await ensure_archive_upload_ready_for_sha256(upload_id)

    async def run() -> AsyncGenerator[TaskProgress]:
        async with aclosing(iter_archive_upload_sha256_events(upload_id)) as events:
            async for event in events:
                yield TaskProgress(progress=event.percent, message="服务端 SHA256 校验完成" if event.event_type == "complete" else "正在计算服务端 SHA256",
                                   result=event.model_dump(mode="json"))

    submitted = await get_task_manager().submit_durable(
        TaskType.ARCHIVE_HASH, f"校验存档 {session.filename}", run(), actor_id=actor_id,
        resources=(ResourceReference("upload", path=upload_id),), exclusive_key=f"archive-hash:{upload_id}",
    )
    session.hash_task_id = submitted.task_id
    return TaskAccepted(task_id=submitted.task_id)


async def submit_archive_publication(
    upload_id: str, request: ArchiveUploadVerifyRequest, actor_id: int,
) -> TaskAccepted:
    from .application import STAGE_PREFIX, archive_claims

    session = await _get_session(upload_id)
    if session.publish_task_id:
        task = get_task_manager().get_task(session.publish_task_id)
        if task and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.COMPLETED):
            if request.sha256.lower() != session.server_sha256:
                raise HTTPException(status_code=409, detail="校验值与已提交的发布任务不一致")
            return TaskAccepted(task_id=task.task_id)
    async with session.lock:
        await validate_archive_digest(session, request)
    stage = session.target_dir / f"{STAGE_PREFIX}{session.upload_id.replace('-', '')}.tmp"

    async def run() -> AsyncGenerator[TaskProgress]:
        yield TaskProgress(message="正在验证并发布存档文件")
        result = await verify_archive_upload(upload_id, request, actor_id=actor_id)
        yield TaskProgress(progress=100, message="存档上传完成", result=result.model_dump(mode="json"))

    submitted = await get_task_manager().submit_durable(
        TaskType.ARCHIVE_PUBLISH, f"发布存档 {session.filename}", run(), actor_id=actor_id,
        claims=await archive_claims(session.base_path, [session.target_path, stage]), cancellable=False,
        exclusive_key=f"archive-publish:{upload_id}",
    )
    session.publish_task_id = submitted.task_id
    return TaskAccepted(task_id=submitted.task_id)


async def _iter_file_sha256_events(
    file_path: Path, filename: str
) -> AsyncGenerator[ArchiveSHA256Event]:
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
            chunk = await finalize(f.read(ARCHIVE_UPLOAD_CHUNK_SIZE))
            if not chunk:
                break
            await finalize(asyncio.to_thread(hasher.update, chunk))
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
) -> AsyncGenerator[ArchiveSHA256Event]:
    session = await _get_session(upload_id)
    async with session.lock:
        offset = await _session_offset(session)
        if offset != session.size or session.state == "receiving":
            raise HTTPException(status_code=409, detail="Upload is not complete")

        async with aclosing(_iter_file_sha256_events(session.temp_path, session.filename)) as events:
            async for event in events:
                if event.event_type == "complete" and event.sha256:
                    session.state = "hashed"
                    session.server_sha256 = event.sha256
                    session.expires_at = _new_expiry()
                yield event


async def validate_archive_digest(session: ArchiveUploadSession, request: ArchiveUploadVerifyRequest) -> str:
    if session.state != "hashed" or not session.server_sha256:
        raise HTTPException(status_code=409, detail="服务端 SHA256 校验尚未完成")
    digest = request.sha256.lower()
    if digest != session.server_sha256:
        await _delete_upload_temp(session)
        async with get_archive_upload_lock():
            get_archive_upload_sessions().pop(session.upload_id, None)
        raise HTTPException(status_code=409, detail="SHA256 校验失败")
    return digest


async def verify_archive_upload(
    upload_id: str, request: ArchiveUploadVerifyRequest, *, actor_id: int | None = None,
) -> ArchiveUploadVerifyResponse:
    session = await _get_session(upload_id)
    async with session.lock:
        client_sha256 = await validate_archive_digest(session, request)

        async def publish() -> ArchiveUploadVerifyResponse:
            await _publish_archive_upload(session, actor_id=actor_id)
            response = ArchiveUploadVerifyResponse(
                upload_id=upload_id,
                path=session.archive_path,
                filename=session.filename,
                sha256=client_sha256,
            )
            session.state = "published"
            session.expires_at = _new_expiry()
            return response
        return await finalize(publish())
