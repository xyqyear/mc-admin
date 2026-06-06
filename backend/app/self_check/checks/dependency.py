import asyncio
import os
import shutil
from pathlib import Path

from ...config import settings
from ..types import SelfCheckFindingResult
from .base import CheckDefinition, SelfCheckContext, finding, success


def binary_available(path_or_name: str | Path) -> bool:
    value = str(path_or_name)
    candidate = Path(value)
    if candidate.is_absolute() or "/" in value:
        return candidate.is_file() and os.access(candidate, os.X_OK)
    return shutil.which(value) is not None


async def check_binary_dependencies(
    context: SelfCheckContext,
) -> list[SelfCheckFindingResult]:
    definition = DEFINITIONS["dependency.binaries"]
    binaries: dict[str, str | Path] = {
        "fd": settings.fd_binary_path,
        "mcmap": settings.mcmap_binary_path,
        "docker": "docker",
        "7z": "7z",
    }
    if settings.restic is not None:
        binaries["restic"] = settings.restic_binary_path

    missing = [
        {"name": name, "path": str(path)}
        for name, path in binaries.items()
        if not await asyncio.to_thread(binary_available, path)
    ]
    if missing:
        return [
            finding(
                check_id=definition.check_id,
                category=definition.category,
                severity="warning",
                status="warning",
                title=definition.title,
                message="一个或多个必需的命令行依赖不存在，或没有执行权限。",
                evidence={"missing": missing},
                remediation=["安装缺失的命令行程序，或更新 config.toml 中的路径配置。"],
            )
        ]
    return success(definition, "必需的命令行依赖均可用。")


DEFINITIONS: dict[str, CheckDefinition] = {
    definition.check_id: definition
    for definition in [
        CheckDefinition(
            "dependency.binaries",
            "dependency",
            "命令行依赖",
            "检查系统所需的命令行程序是否可用。",
            check_binary_dependencies,
        ),
    ]
}


_binary_available = binary_available
_check_binary_dependencies = check_binary_dependencies
