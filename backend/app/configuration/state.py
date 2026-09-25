import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import aiofiles
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.servers.models import Server

from ..minecraft.paths import find_compose_file, resolve_server_paths
from ..servers.crud import get_active_server_by_id
from ..utils import async_fs
from .preparation import ServerConfiguration


class ConfigurationConflict(HTTPException):
    code = "configuration_conflict"

    def __init__(self, current_version: str) -> None:
        super().__init__(status_code=409, detail={
            "code": self.code,
            "message": "配置已被其他操作修改，请重新比较后提交",
            "current_version": current_version,
        })


def source_fingerprint(template_id: int | None, snapshot_json: str | None, values_json: str | None) -> str:
    value = json.dumps([template_id, snapshot_json, values_json], ensure_ascii=False)
    return hashlib.sha256(value.encode()).hexdigest()


def prepared_source_fingerprint(configuration: ServerConfiguration) -> str:
    snapshot = configuration.template_snapshot
    return source_fingerprint(snapshot.template_id if snapshot else None, configuration.snapshot_json, configuration.values_json)


@dataclass(frozen=True)
class ConfigurationState:
    server_generation: int
    compose_path: Path
    content: bytes
    template_id: int | None
    snapshot_json: str | None
    values_json: str | None

    @property
    def yaml_content(self) -> str:
        return self.content.decode("utf-8")

    @property
    def source_version(self) -> str:
        return source_fingerprint(self.template_id, self.snapshot_json, self.values_json)

    @property
    def version(self) -> str:
        digest = hashlib.sha256()
        digest.update(f"{self.server_generation}:{self.compose_path}:{self.source_version}:".encode())
        digest.update(self.content)
        return digest.hexdigest()

    def check_version(self, expected_version: str | None) -> None:
        if expected_version is not None and expected_version != self.version:
            raise ConfigurationConflict(self.version)


async def read_configuration_state(
    db: AsyncSession, server_id: str, servers_root: Path,
) -> ConfigurationState:
    server = await get_active_server_by_id(db, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="服务器不存在")
    paths = await resolve_server_paths(servers_root, server_id)
    compose = await find_compose_file(paths)
    if compose is None:
        raise HTTPException(status_code=404, detail="服务器 Compose 文件不存在")
    compose = await async_fs.resolve_inside(paths.project_path, compose)
    async with aiofiles.open(compose, "rb") as stream:
        content = await stream.read()
    return ConfigurationState(server.id, compose, content, server.template_id, server.template_snapshot_json, server.variable_values_json)


async def save_configuration_metadata(
    db: AsyncSession, server_id: str, configuration: ServerConfiguration, *, generation: int | None = None,
) -> None:
    server = await get_active_server_by_id(db, server_id)
    if server is None or (generation is not None and server.id != generation):
        raise HTTPException(status_code=409, detail="服务器实例已变更，请重新发起操作")
    snapshot = configuration.template_snapshot
    server.template_id = snapshot.template_id if snapshot else None
    server.template_snapshot_json = configuration.snapshot_json
    server.variable_values_json = configuration.values_json
    server.updated_at = datetime.now(UTC)
    await db.flush()


async def clear_template_configuration(db: AsyncSession, server: Server) -> None:
    await save_configuration_metadata(db, server.server_id, ServerConfiguration(""), generation=server.id)
    await db.commit()
