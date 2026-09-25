import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from ..config import get_settings
from ..errors import PublicOperationError
from ..servers.references import ServerRef
from ..utils.exec import exec_command

PRUNE_INPUT_SCHEMA = 1
MCMAP_PRUNE_VERSION = "mcmap 0.8.4"


class PrunePreviewConflict(HTTPException):
    def __init__(self, reason: str) -> None:
        messages = {
            "expired": "裁剪预览已过期，请重新预览后再应用",
            "stale": "世界数据或领地保护信息已变化，请重新预览后再应用",
            "consumed": "该预览已提交过应用，请重新预览后再操作",
        }
        super().__init__(409, detail={"code": f"prune_preview_{reason}", "message": messages[reason]})


def payload_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _manifest(data_path: Path) -> str:
    root = data_path.resolve()
    identity = root.stat()
    entries: list[tuple] = [(".", identity.st_dev, identity.st_ino)]
    seen: set[tuple[int, int]] = set()
    for directory, children, files in os.walk(root, followlinks=True):
        parent = Path(directory)
        resolved = parent.resolve()
        if not resolved.is_relative_to(root):
            raise PublicOperationError("世界扫描路径超出服务器数据目录，请检查符号链接")
        stat = resolved.stat()
        key = (stat.st_dev, stat.st_ino)
        if key in seen:
            children.clear()
            continue
        seen.add(key)
        children[:] = sorted(name for name in children if name != ".mcmap")
        if parent.is_symlink():
            entries.append((parent.relative_to(root).as_posix(), "link", os.readlink(parent)))
        for name in sorted(files):
            if not (name.endswith((".mca", ".mcc")) or name == "level.dat" or (parent == root and name == "server.properties")):
                continue
            path = parent / name
            if not path.resolve().is_relative_to(root):
                raise PublicOperationError("世界文件超出服务器数据目录，请检查符号链接")
            stat = path.stat()
            entries.append((path.relative_to(root).as_posix(), stat.st_dev, stat.st_ino,
                            stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
    return payload_digest(entries)


async def world_manifest(data_path: Path) -> str:
    return await asyncio.to_thread(_manifest, data_path)


async def require_supported_adapter() -> None:
    settings = get_settings()
    version = await exec_command(str(settings.mcmap_binary_path), "--version", timeout=10)
    if version.strip() != MCMAP_PRUNE_VERSION:
        raise PublicOperationError("裁剪需要已验证的 mcmap 0.8.4，请检查应用使用的二进制版本")


@dataclass(frozen=True)
class PruneInputVersion:
    generation: int
    data_path: str
    threshold_ticks: int
    mode: str
    manifest: str
    claims_digest: str

    @property
    def version(self) -> str:
        return payload_digest({"schema": PRUNE_INPUT_SCHEMA, "adapter": MCMAP_PRUNE_VERSION,
                               **self.__dict__})

    @classmethod
    def capture(cls, reference: ServerRef, threshold_ticks: int, mode: str,
                manifest: str, claims_digest: str) -> "PruneInputVersion":
        return cls(reference.generation, str(reference.data_path), threshold_ticks, mode, manifest, claims_digest)
