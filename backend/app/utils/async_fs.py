"""``asyncio.to_thread`` wrappers for filesystem ops aiofiles does not cover.

Use ``aiofiles`` directly when it has the operation; this module covers
``shutil`` calls, ``os.chown``/``chmod``, and CPU-bound PIL work that would
otherwise stall the event loop.
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
from pathlib import Path
from typing import IO, Optional

from PIL import Image


async def iterdir(path: Path) -> list[Path]:
    return await asyncio.to_thread(_iterdir_sync, path)


def _iterdir_sync(path: Path) -> list[Path]:
    return list(path.iterdir())


async def resolve(path: Path, *, strict: bool = False) -> Path:
    """``Path.resolve`` does an lstat per component; can block measurably on deep paths."""
    return await asyncio.to_thread(path.resolve, strict)


class PathOutsideBaseError(ValueError):
    """A user-supplied path resolved outside its required base directory."""


async def resolve_inside(base: Path, candidate: Path) -> Path:
    """Resolve ``candidate`` and require it to stay under (or equal) resolved ``base``.

    Symlinks are followed before the containment check, so a link pointing
    outside ``base`` is rejected. Raises ``PathOutsideBaseError`` on escape.
    """
    resolved_base = await resolve(base)
    resolved = await resolve(candidate)
    if not resolved.is_relative_to(resolved_base):
        raise PathOutsideBaseError(
            f"Path {candidate} resolves to {resolved}, outside {resolved_base}"
        )
    return resolved


async def touch(path: Path, *, exist_ok: bool = True) -> None:
    await asyncio.to_thread(_touch_sync, path, exist_ok)


def _touch_sync(path: Path, exist_ok: bool) -> None:
    path.touch(exist_ok=exist_ok)


async def rmtree(path: Path | str, *, ignore_errors: bool = False) -> None:
    await asyncio.to_thread(shutil.rmtree, path, ignore_errors)


async def copy2(src: Path | str, dst: Path | str) -> Path | str:
    return await asyncio.to_thread(shutil.copy2, src, dst)


async def copytree(
    src: Path | str,
    dst: Path | str,
    *,
    dirs_exist_ok: bool = False,
) -> Path | str:
    return await asyncio.to_thread(_copytree_sync, src, dst, dirs_exist_ok)


def _copytree_sync(src, dst, dirs_exist_ok: bool):
    return shutil.copytree(src, dst, dirs_exist_ok=dirs_exist_ok)


async def move(src: Path | str, dst: Path | str) -> Path | str:
    return await asyncio.to_thread(shutil.move, src, dst)


async def disk_usage(path: Path | str) -> shutil._ntuple_diskusage:
    return await asyncio.to_thread(shutil.disk_usage, path)


async def copyfileobj(src: IO[bytes], dst: IO[bytes], length: int = 16 * 1024) -> None:
    await asyncio.to_thread(shutil.copyfileobj, src, dst, length)


async def chown(path: Path | str, uid: int, gid: int) -> None:
    await asyncio.to_thread(os.chown, path, uid, gid)


async def chmod(path: Path | str, mode: int) -> None:
    await asyncio.to_thread(os.chmod, path, mode)


async def extract_skin_avatar(skin_bytes: bytes) -> bytes:
    """Crop the 8x8 face from a skin PNG; runs in a thread because PIL holds the GIL."""
    return await asyncio.to_thread(_extract_skin_avatar_sync, skin_bytes)


def _extract_skin_avatar_sync(skin_bytes: bytes) -> bytes:
    skin_image = Image.open(io.BytesIO(skin_bytes))
    avatar = skin_image.crop((8, 8, 16, 16))
    output = io.BytesIO()
    avatar.save(output, format="PNG")
    return output.getvalue()
