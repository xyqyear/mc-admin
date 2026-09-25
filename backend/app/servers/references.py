from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.servers.models import Server, ServerStatus

from ..minecraft.paths import (
    find_compose_file,
    resolve_server_paths,
    validate_server_name,
)


@dataclass(frozen=True)
class ServerRef:
    server_id: str
    generation: int
    servers_root: Path
    project_path: Path
    data_path: Path

    @property
    def server_db_id(self) -> int:
        return self.generation

    @property
    def incarnation(self) -> int:
        return self.generation


async def resolve_server_ref(
    session: AsyncSession,
    server_id: str,
    *,
    servers_root: Path,
    require_exists: bool = True,
) -> ServerRef:
    validate_server_name(server_id)
    result = await session.execute(
        select(Server.id, Server.status).where(Server.server_id == server_id)
    )
    rows = result.all()
    active_ids = [row.id for row in rows if row.status == ServerStatus.ACTIVE]
    if len(active_ids) > 1:
        raise HTTPException(status_code=409, detail="存在重复的活动服务器记录，请先核对实例归属")
    if not active_ids:
        if rows:
            raise HTTPException(status_code=409, detail="服务器实例已停用，请显式接管现有目录后重试")
        raise HTTPException(status_code=404, detail="服务器尚未登记；已有目录需要先显式接管")

    paths = await resolve_server_paths(servers_root, server_id)
    if require_exists and await find_compose_file(paths) is None:
        raise HTTPException(status_code=404, detail="服务器项目或 Compose 文件缺失，请检查目录或同步服务器状态")
    return ServerRef(server_id, active_ids[0], paths.servers_root, paths.project_path, paths.data_path)


async def revalidate_server_ref(
    session: AsyncSession,
    reference: ServerRef,
    *,
    require_exists: bool = True,
) -> ServerRef:
    current = await resolve_server_ref(
        session,
        reference.server_id,
        servers_root=reference.servers_root,
        require_exists=require_exists,
    )
    if current.generation != reference.generation:
        raise HTTPException(status_code=409, detail="服务器实例已变更，请重新发起操作")
    if current != reference:
        raise HTTPException(status_code=409, detail="服务器目录归属已变更，请重新发起操作")
    return current
