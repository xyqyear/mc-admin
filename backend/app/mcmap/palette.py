"""Palette hash computation and invalidation check."""

import hashlib
from pathlib import Path
from typing import Optional

from .cache import ServerMapCache


def compute_palette_hash(version: str, mods_dir: Optional[Path]) -> str:
    """SHA256 over game version + sorted mod jar filenames."""
    parts = [version]
    if mods_dir is not None and mods_dir.is_dir():
        parts.extend(sorted(p.name for p in mods_dir.iterdir() if p.suffix == ".jar"))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def palette_is_current(
    cache: ServerMapCache, version: str, mods_dir: Optional[Path]
) -> bool:
    if not cache.palette_json.exists() or not cache.palette_hash_file.exists():
        return False
    expected = compute_palette_hash(version, mods_dir)
    return cache.palette_hash_file.read_text().strip() == expected


def write_palette_hash(
    cache: ServerMapCache, version: str, mods_dir: Optional[Path]
) -> None:
    cache.palette_hash_file.write_text(compute_palette_hash(version, mods_dir))
    cache.chown_to_data_owner(cache.palette_hash_file)


def discover_mods_dir(data_path: Path) -> Optional[Path]:
    """Return data/mods if it exists and contains at least one .jar; else None."""
    mods = data_path / "mods"
    if not mods.is_dir():
        return None
    if not any(p.suffix == ".jar" for p in mods.iterdir()):
        return None
    return mods
