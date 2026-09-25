from dataclasses import dataclass
from pathlib import Path

from aiofiles import os as aioos
from fastapi import HTTPException

from ..utils import async_fs

COMPOSE_FILE_NAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")


class ServerPathError(HTTPException):
    pass


def validate_server_name(name: str) -> None:
    if not name or name in {".", ".."} or "/" in name or "\x00" in name:
        raise ServerPathError(status_code=400, detail="服务器名称必须是有效的单级目录名称")


@dataclass(frozen=True)
class ServerPaths:
    servers_root: Path
    project_path: Path
    data_path: Path


async def resolve_server_paths(servers_root: Path, name: str) -> ServerPaths:
    validate_server_name(name)
    try:
        root = await async_fs.resolve(servers_root)
        project = root / name
        resolved_project = await async_fs.resolve(project)
        if resolved_project != project:
            raise ServerPathError(
                status_code=409,
                detail="服务器项目目录不能通过符号链接指向其他目录，请修复目录归属后重试",
            )
        data = await async_fs.resolve(project / "data")
        if data == project or not data.is_relative_to(project):
            raise ServerPathError(
                status_code=409,
                detail="服务器数据目录超出所属项目范围，请修复符号链接后重试",
            )
        return ServerPaths(root, project, data)
    except (OSError, RuntimeError):
        raise ServerPathError(status_code=409, detail="无法校验服务器目录，请检查目录及符号链接") from None


async def confined_server_file(base: Path, candidate: Path) -> Path:
    try:
        await async_fs.resolve_inside(base, candidate)
    except (async_fs.PathOutsideBaseError, OSError, RuntimeError):
        raise ServerPathError(status_code=409, detail="服务器文件超出所属目录范围，请检查符号链接") from None
    return candidate


async def find_compose_file(paths: ServerPaths) -> Path | None:
    for filename in COMPOSE_FILE_NAMES:
        candidate = paths.project_path / filename
        # Dangling links must be checked too: creation could otherwise write outside the project.
        await confined_server_file(paths.project_path, candidate)
        if await aioos.path.isfile(candidate):
            return candidate
    return None
