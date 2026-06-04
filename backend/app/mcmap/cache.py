"""Filesystem layout and freshness checks for the per-server mcmap cache."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal

import aiofiles.os as aioos

from ..logger import logger
from ..utils import async_fs

FreshnessState = Literal["fresh", "stale", "missing_mca", "missing_png"]


@dataclass
class ServerMapCache:
    """Path resolver and freshness checker for a server's ``data/.mcmap/`` tree.

    Brokers ownership: backend-created dirs/files inside ``.mcmap/`` are
    chowned to the data dir's owner so the demoted mcmap subprocess can
    write into them.
    """

    data_path: Path

    @property
    def cache_dir(self) -> Path:
        return self.data_path / ".mcmap"

    @property
    def client_jar(self) -> Path:
        return self.cache_dir / "client.jar"

    @property
    def palette_json(self) -> Path:
        return self.cache_dir / "palette.json"

    @property
    def palette_hash_file(self) -> Path:
        return self.cache_dir / "palette.hash"

    def tiles_dir(self, region_path: str) -> Path:
        return self.cache_dir / "tiles" / region_path

    def mca_path(self, region_path: str, x: int, z: int) -> Path:
        return self.data_path / region_path / f"r.{x}.{z}.mca"

    def png_path(self, region_path: str, x: int, z: int) -> Path:
        return self.tiles_dir(region_path) / f"r.{x}.{z}.png"

    async def is_fresh(self, region_path: str, x: int, z: int) -> FreshnessState:
        mca = self.mca_path(region_path, x, z)
        try:
            mca_st = await aioos.stat(mca)
        except FileNotFoundError:
            return "missing_mca"
        # Zero-byte MCAs make fastanvil raise UnexpectedEof on header read; treat as absent.
        if mca_st.st_size == 0:
            return "missing_mca"
        png = self.png_path(region_path, x, z)
        try:
            png_st = await aioos.stat(png)
        except FileNotFoundError:
            return "missing_png"
        # Windows-mounted worlds can expose fractional MCA mtimes while mcmap
        # writes PNG mtimes at second precision.
        if int(mca_st.st_mtime) == int(png_st.st_mtime):
            return "fresh"
        return "stale"

    async def chown_to_data_owner(self, path: Path) -> None:
        """Chown ``path`` to match ``data_path``; no-op unless the backend runs as root."""
        if os.geteuid() != 0:
            return
        try:
            st = await aioos.stat(self.data_path)
        except FileNotFoundError:
            return
        try:
            await async_fs.chown(path, st.st_uid, st.st_gid)
        except OSError as e:
            logger.warning("mcmap: failed to chown %s: %s", path, e)

    async def ensure_dir(self, target: Path) -> None:
        """Create ``target`` (with parents) and chown new levels under ``data_path``.

        ``target`` must live inside ``data_path`` so the chown walk never
        touches directories outside the server's data tree.
        """
        try:
            target.relative_to(self.data_path)
        except ValueError as exc:
            raise ValueError(
                f"{target} is not inside data_path {self.data_path}"
            ) from exc

        to_create: List[Path] = []
        p = target
        while not await aioos.path.exists(p) and p != self.data_path:
            to_create.append(p)
            if p.parent == p:
                break
            p = p.parent

        await aioos.makedirs(target, exist_ok=True)

        for created in reversed(to_create):
            await self.chown_to_data_owner(created)
