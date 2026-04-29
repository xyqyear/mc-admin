"""Filesystem layout and freshness checks for the per-server mcmap cache."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal

from ..logger import logger

FreshnessState = Literal["fresh", "stale", "missing_mca", "missing_png"]


@dataclass
class ServerMapCache:
    """Path resolver and freshness checker for a server's `data/.mcmap/` tree.

    Also brokers ownership: the mcmap subprocess runs demoted to the data
    dir's uid/gid, so any directories or files the backend creates inside
    `.mcmap/` must be chowned to that same owner — otherwise the demoted
    subprocess can't write into them.
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

    def is_fresh(self, region_path: str, x: int, z: int) -> FreshnessState:
        mca = self.mca_path(region_path, x, z)
        try:
            mca_st = mca.stat()
        except FileNotFoundError:
            return "missing_mca"
        # Zero-byte MCAs cannot be parsed (fastanvil raises UnexpectedEof on
        # the header read). Treat them as absent so the tile endpoint short-
        # circuits to 404 without ever queuing an mcmap render.
        if mca_st.st_size == 0:
            return "missing_mca"
        png = self.png_path(region_path, x, z)
        if not png.exists():
            return "missing_png"
        # mcmap renders with `--preserve-mtime`, so a PNG that matches its
        # source MCA's mtime exactly is current; any divergence means the
        # MCA was modified after rendering and the tile must be regenerated.
        if mca_st.st_mtime == png.stat().st_mtime:
            return "fresh"
        return "stale"

    def chown_to_data_owner(self, path: Path) -> None:
        """Chown ``path`` to match ``data_path`` ownership.

        No-op when the backend is not running as root (typical for dev), or
        when ``data_path`` itself is missing.
        """
        if os.geteuid() != 0:
            return
        try:
            st = os.stat(self.data_path)
        except FileNotFoundError:
            return
        try:
            os.chown(path, st.st_uid, st.st_gid)
        except OSError as e:
            logger.warning("mcmap: failed to chown %s: %s", path, e)

    def ensure_dir(self, target: Path) -> None:
        """Create ``target`` (with parents) and chown each newly created level
        under ``data_path`` to the data dir's owner.

        ``target`` must live inside ``data_path``; the chown walk stops there
        so we never touch directories outside the server's data tree.
        """
        try:
            target.relative_to(self.data_path)
        except ValueError as exc:
            raise ValueError(
                f"{target} is not inside data_path {self.data_path}"
            ) from exc

        to_create: List[Path] = []
        p = target
        while not p.exists() and p != self.data_path:
            to_create.append(p)
            if p.parent == p:
                break
            p = p.parent

        target.mkdir(parents=True, exist_ok=True)

        for created in reversed(to_create):
            self.chown_to_data_owner(created)
