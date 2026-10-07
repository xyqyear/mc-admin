"""``asyncio.to_thread`` wrappers for filesystem ops aiofiles does not cover.

Use ``aiofiles`` directly when it has the operation; this module covers
``shutil`` calls, ``os.chown``/``chmod``, and CPU-bound PIL work that would
otherwise stall the event loop.
"""

from __future__ import annotations

import asyncio
import ctypes
import errno
import io
import os
import shutil
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Protocol

from PIL import Image

from ..operations.finalization import finalize


async def iterdir(path: Path) -> list[Path]:
    return await asyncio.to_thread(_iterdir_sync, path)


@dataclass
class TreeDirectoryCursor:
    path: str
    offset: int
    stamp: tuple[int, int, int]


@dataclass
class TreePageCursor:
    root_index: int
    directories: list[TreeDirectoryCursor]


class TreeChangedError(ValueError):
    pass


class _DirectoryIterator(Protocol):
    def __next__(self) -> os.DirEntry[str]: ...

    def close(self) -> None: ...


async def tree_page(
    base: Path, roots: Sequence[str], *, cursor: TreePageCursor | None, limit: int,
) -> tuple[list[tuple[str, str, int, str | None]], TreePageCursor | None]:
    return await asyncio.to_thread(_tree_page_sync, base, roots, cursor, limit)


def _tree_page_sync(
    base: Path, roots: Sequence[str], cursor: TreePageCursor | None, limit: int,
) -> tuple[list[tuple[str, str, int, str | None]], TreePageCursor | None]:
    boundary = base.resolve()
    state = cursor or TreePageCursor(0, [])
    iterators: list[_DirectoryIterator] = []
    rows: list[tuple[str, str, int, str | None]] = []

    def directory_stamp(path: Path) -> tuple[int, int, int]:
        metadata = path.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or not path.resolve().is_relative_to(boundary):
            raise TreeChangedError()
        return metadata.st_dev, metadata.st_ino, metadata.st_mtime_ns

    def visit(path: Path) -> None:
        relative = path.relative_to(base).as_posix()
        relative = "" if relative == "." else relative
        try:
            if not path.resolve().is_relative_to(boundary):
                rows.append((relative, "", 0, "路径越界，无法下载"))
                return
            metadata = path.stat()
            if stat.S_ISDIR(metadata.st_mode):
                if path.is_symlink():
                    rows.append((relative, "", 0, "不支持递归下载符号链接目录"))
                    return
                stamp = directory_stamp(path)
                iterator = os.scandir(path)
                state.directories.append(TreeDirectoryCursor(relative, 0, stamp))
                iterators.append(iterator)
                if relative:
                    rows.append((relative, "directory", 0, None))
            elif stat.S_ISREG(metadata.st_mode):
                rows.append((relative, "file", metadata.st_size, None))
            else:
                rows.append((relative, "", 0, "不支持下载此文件类型"))
        except OSError:
            rows.append((relative, "", 0, "文件已变化或无法读取，请刷新后重试"))

    try:
        for directory in state.directories:
            path = base / directory.path
            if directory_stamp(path) != directory.stamp:
                raise TreeChangedError()
            iterator = os.scandir(path)
            iterators.append(iterator)
            for _ in range(directory.offset):
                if next(iterator, None) is None:
                    raise TreeChangedError()
        while len(rows) < limit:
            if iterators:
                child = next(iterators[-1], None)
                if child is None:
                    iterators.pop().close()
                    state.directories.pop()
                    continue
                state.directories[-1].offset += 1
                visit(Path(child.path))
            elif state.root_index < len(roots):
                root = roots[state.root_index]
                state.root_index += 1
                visit(base / root)
            else:
                return rows, None
        return rows, state if iterators or state.root_index < len(roots) else None
    finally:
        for iterator in iterators:
            iterator.close()


async def lexists(path: Path) -> bool:
    return await asyncio.to_thread(os.path.lexists, path)


async def lexists_many(paths: Sequence[Path]) -> tuple[bool, ...]:
    return await asyncio.to_thread(_lexists_many_sync, tuple(paths))


def _lexists_many_sync(paths: Sequence[Path]) -> tuple[bool, ...]:
    return tuple(os.path.lexists(path) for path in paths)


def _iterdir_sync(path: Path) -> list[Path]:
    return list(path.iterdir())


async def resolve(path: Path, *, strict: bool = False) -> Path:
    """``Path.resolve`` does an lstat per component; can block measurably on deep paths."""
    return await asyncio.to_thread(path.resolve, strict)


class PathOutsideBaseError(ValueError):
    """A user-supplied path resolved outside its required base directory."""


async def resolve_many(
    paths: Sequence[Path], *, base: Path | None = None
) -> tuple[Path, ...]:
    return await asyncio.to_thread(_resolve_many_sync, tuple(paths), base)


def _resolve_many_sync(
    paths: Sequence[Path], base: Path | None
) -> tuple[Path, ...]:
    boundary = base.resolve() if base is not None else None
    resolved = []
    for path in paths:
        actual = path.resolve()
        if boundary is not None and not actual.is_relative_to(boundary):
            raise PathOutsideBaseError(
                f"Path {path} resolves to {actual}, outside {boundary}"
            )
        resolved.append(actual)
    return tuple(resolved)


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
    await finalize(asyncio.to_thread(_touch_sync, path, exist_ok))


def _touch_sync(path: Path, exist_ok: bool) -> None:
    path.touch(exist_ok=exist_ok)


async def rmtree(path: Path | str, *, ignore_errors: bool = False) -> None:
    await finalize(asyncio.to_thread(shutil.rmtree, path, ignore_errors))


async def copy2(src: Path | str, dst: Path | str) -> Path | str:
    return await finalize(asyncio.to_thread(shutil.copy2, src, dst))


async def copytree(
    src: Path | str,
    dst: Path | str,
    *,
    dirs_exist_ok: bool = False,
) -> Path | str:
    return await finalize(asyncio.to_thread(_copytree_sync, src, dst, dirs_exist_ok))


def _copytree_sync(src, dst, dirs_exist_ok: bool):
    return shutil.copytree(src, dst, dirs_exist_ok=dirs_exist_ok)


async def move(src: Path | str, dst: Path | str) -> Path | str:
    return await finalize(asyncio.to_thread(shutil.move, src, dst))


async def exchange(left: Path, right: Path) -> None:
    """Atomically swap two existing paths on the same Linux filesystem."""
    await finalize(asyncio.to_thread(_exchange_sync, left, right))


def _exchange_sync(left: Path, right: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    number = {"x86_64": 316, "aarch64": 276}.get(os.uname().machine)
    if number is None:
        raise OSError(errno.ENOSYS, "Atomic path exchange is unavailable on this architecture")
    # Alpine's musl lacks the renameat2 wrapper; AT_FDCWD = -100, RENAME_EXCHANGE = 2.
    libc.syscall.restype = ctypes.c_long
    if libc.syscall(ctypes.c_long(number), ctypes.c_int(-100), ctypes.c_char_p(os.fsencode(left)),
                    ctypes.c_int(-100), ctypes.c_char_p(os.fsencode(right)), ctypes.c_uint(2)) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


async def disk_usage(path: Path | str) -> shutil._ntuple_diskusage:
    return await asyncio.to_thread(shutil.disk_usage, path)


async def copyfileobj(src: IO[bytes], dst: IO[bytes], length: int = 16 * 1024) -> None:
    await finalize(asyncio.to_thread(shutil.copyfileobj, src, dst, length))


async def chown(path: Path | str, uid: int, gid: int) -> None:
    await finalize(asyncio.to_thread(os.chown, path, uid, gid))


async def chmod(path: Path | str, mode: int) -> None:
    await finalize(asyncio.to_thread(os.chmod, path, mode))


async def extract_skin_avatar(skin_bytes: bytes) -> bytes:
    """Crop the 8x8 face from a skin PNG; runs in a thread because PIL holds the GIL."""
    return await asyncio.to_thread(_extract_skin_avatar_sync, skin_bytes)


def _extract_skin_avatar_sync(skin_bytes: bytes) -> bytes:
    skin_image = Image.open(io.BytesIO(skin_bytes))
    avatar = skin_image.crop((8, 8, 16, 16))
    output = io.BytesIO()
    avatar.save(output, format="PNG")
    return output.getvalue()
