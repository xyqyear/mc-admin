"""
Async wrappers for filesystem and system operations that aiofiles does not
provide. All wrappers off-load to a worker thread via ``asyncio.to_thread``.

When ``aiofiles`` covers the operation (open, stat, exists, mkdir, makedirs,
listdir, rename, remove, unlink, rmdir, replace, samefile, isdir, isfile,
islink), call ``aiofiles`` directly at the call site — do NOT add a wrapper
here for those.

Benchmarks in ``backend/benchmarks/sync_in_async_bench.py`` justify the
threaded approach: the per-call overhead is ~50–200 µs, but tail event-loop
stall drops from tens-to-hundreds of milliseconds to single-digit
milliseconds under concurrent load.
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
from pathlib import Path
from typing import IO, Optional

from PIL import Image


# ---------------------------------------------------------------------------
# pathlib helpers (no aiofiles equivalent)
# ---------------------------------------------------------------------------


async def iterdir(path: Path) -> list[Path]:
    """Return ``path``'s entries as a list of ``Path`` objects.

    Off-loaded so the directory walk runs on a worker thread.
    """
    return await asyncio.to_thread(_iterdir_sync, path)


def _iterdir_sync(path: Path) -> list[Path]:
    return list(path.iterdir())


async def resolve(path: Path, *, strict: bool = False) -> Path:
    """Resolve symlinks. ``Path.resolve`` makes lstat syscalls per component,
    so it can block measurably on deep paths.
    """
    return await asyncio.to_thread(path.resolve, strict)


async def touch(path: Path, *, exist_ok: bool = True) -> None:
    """Create an empty file (or update mtime if it exists)."""
    await asyncio.to_thread(_touch_sync, path, exist_ok)


def _touch_sync(path: Path, exist_ok: bool) -> None:
    path.touch(exist_ok=exist_ok)


# ---------------------------------------------------------------------------
# shutil
# ---------------------------------------------------------------------------


async def rmtree(path: Path | str, *, ignore_errors: bool = False) -> None:
    """Recursively remove a directory tree."""
    await asyncio.to_thread(shutil.rmtree, path, ignore_errors)


async def copy2(src: Path | str, dst: Path | str) -> Path | str:
    """Copy a file with metadata (mtime preserved). Returns the destination."""
    return await asyncio.to_thread(shutil.copy2, src, dst)


async def copytree(
    src: Path | str,
    dst: Path | str,
    *,
    dirs_exist_ok: bool = False,
) -> Path | str:
    """Recursively copy a directory tree."""
    return await asyncio.to_thread(_copytree_sync, src, dst, dirs_exist_ok)


def _copytree_sync(src, dst, dirs_exist_ok: bool):
    return shutil.copytree(src, dst, dirs_exist_ok=dirs_exist_ok)


async def move(src: Path | str, dst: Path | str) -> Path | str:
    """Move a file or directory (recursive when crossing filesystems)."""
    return await asyncio.to_thread(shutil.move, src, dst)


async def disk_usage(path: Path | str) -> shutil._ntuple_diskusage:
    """Return a ``(total, used, free)`` named tuple in bytes."""
    return await asyncio.to_thread(shutil.disk_usage, path)


async def copyfileobj(src: IO[bytes], dst: IO[bytes], length: Optional[int] = None) -> None:
    """Copy file object data without loading into memory."""
    if length is None:
        await asyncio.to_thread(shutil.copyfileobj, src, dst)
    else:
        await asyncio.to_thread(shutil.copyfileobj, src, dst, length)


# ---------------------------------------------------------------------------
# os
# ---------------------------------------------------------------------------


async def chown(path: Path | str, uid: int, gid: int) -> None:
    """Change ownership."""
    await asyncio.to_thread(os.chown, path, uid, gid)


async def chmod(path: Path | str, mode: int) -> None:
    """Change permissions."""
    await asyncio.to_thread(os.chmod, path, mode)


# ---------------------------------------------------------------------------
# CPU-bound (PIL)
# ---------------------------------------------------------------------------


async def extract_skin_avatar(skin_bytes: bytes) -> bytes:
    """Crop the 8×8 face region from a Minecraft skin PNG and return PNG bytes.

    PIL holds the GIL during decode/encode, so we off-load to a thread.
    """
    return await asyncio.to_thread(_extract_skin_avatar_sync, skin_bytes)


def _extract_skin_avatar_sync(skin_bytes: bytes) -> bytes:
    skin_image = Image.open(io.BytesIO(skin_bytes))
    avatar = skin_image.crop((8, 8, 16, 16))
    output = io.BytesIO()
    avatar.save(output, format="PNG")
    return output.getvalue()
