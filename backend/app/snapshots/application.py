"""Backup application ownership around the existing Restic coverage rules."""

from pathlib import Path

from fastapi import HTTPException

from ..minecraft import DockerMCManager
from ..utils import async_fs


class SnapshotMaintenanceConflict(Exception):
    pass


async def resolve_backup_paths(manager: DockerMCManager, root: Path, server_id: str | None, paths: list[str] | None) -> list[Path]:
    if not server_id and not paths:
        return [await async_fs.resolve(root)]
    if not server_id:
        raise HTTPException(status_code=400, detail="Cannot specify paths without server_id")
    instance = manager.get_instance(server_id)
    try:
        project = await async_fs.resolve_inside(root, instance.get_project_path())
        if not paths:
            return [project]
        data = instance.get_data_path()
        return [await async_fs.resolve_inside(data, data / path.lstrip("/")) for path in paths]
    except async_fs.PathOutsideBaseError as error:
        raise HTTPException(status_code=400, detail="路径越界：目标路径不在服务器目录内") from error
