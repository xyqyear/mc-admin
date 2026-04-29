"""Palette hash computation and invalidation check."""

import hashlib
from pathlib import Path
from typing import Optional

import aiofiles
import aiofiles.os as aioos

from ..utils import async_fs
from .cache import ServerMapCache


async def compute_palette_hash(version: str, mods_dir: Optional[Path]) -> str:
    """SHA256 over game version + sorted mod jar filenames."""
    parts = [version]
    if mods_dir is not None and await aioos.path.isdir(mods_dir):
        entries = await async_fs.iterdir(mods_dir)
        parts.extend(sorted(p.name for p in entries if p.suffix == ".jar"))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


async def palette_is_current(
    cache: ServerMapCache, version: str, mods_dir: Optional[Path]
) -> bool:
    if not await aioos.path.exists(cache.palette_json):
        return False
    if not await aioos.path.exists(cache.palette_hash_file):
        return False
    expected = await compute_palette_hash(version, mods_dir)
    async with aiofiles.open(cache.palette_hash_file, "r") as f:
        stored = (await f.read()).strip()
    return stored == expected


async def write_palette_hash(
    cache: ServerMapCache, version: str, mods_dir: Optional[Path]
) -> None:
    digest = await compute_palette_hash(version, mods_dir)
    async with aiofiles.open(cache.palette_hash_file, "w") as f:
        await f.write(digest)
    await cache.chown_to_data_owner(cache.palette_hash_file)


async def discover_mods_dir(data_path: Path) -> Optional[Path]:
    """Return data/mods if it exists and contains at least one .jar; else None."""
    mods = data_path / "mods"
    if not await aioos.path.isdir(mods):
        return None
    entries = await async_fs.iterdir(mods)
    if not any(p.suffix == ".jar" for p in entries):
        return None
    return mods
