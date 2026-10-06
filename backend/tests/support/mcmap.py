import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import Mock


def write_fake_mcmap(content: str, *, prefix: str = "fake_mcmap_") -> Path:
    descriptor, filename = tempfile.mkstemp(suffix=".sh", prefix=prefix)
    os.close(descriptor)
    path = Path(filename)
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def read_fake_mcmap_args(binary: Path) -> list[str]:
    return Path(f"{binary}.args").read_bytes().removesuffix(b"\0").decode().split("\0")


def owned_chown_args(directory: Path) -> list[str]:
    owner = directory.stat()
    return ["--chown", f"{owner.st_uid}:{owner.st_gid}"] if os.geteuid() == 0 else []


def mcmap_config(batch_size: int = 4, thread_count: int = 2) -> Mock:
    config = Mock()
    config.batch_size = batch_size
    config.thread_count = thread_count
    config.request_timeout_seconds = 30
    return config


def build_minimal_world(data_path: Path) -> None:
    (data_path / "server.properties").write_text("level-name=world\n")
    world = data_path / "world"
    (world / "region").mkdir(parents=True)
    (world / "region" / "r.0.0.mca").write_bytes(b"")
    (world / "level.dat").write_bytes(b"")
    nether = world / "DIM-1"
    (nether / "region").mkdir(parents=True)
    (nether / "region" / "r.0.0.mca").write_bytes(b"")
