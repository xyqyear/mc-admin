from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Self

from fastapi import HTTPException
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..files.resources import path_claims
from ..minecraft.paths import validate_server_name
from ..operations.coordinator import ResourceClaim, ResourceKind
from ..servers.models import Server, ServerStatus
from ..servers.references import ServerRef, resolve_server_ref
from ..utils import async_fs
from ..world.selection import resolve_paths, resource_scopes
from .restoration_models import RestorationType
from .selection_models import RestorationSelection


def relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\x00" in value:
        raise ValueError("目标必须是服务器数据目录内的相对路径")
    return path.as_posix()


class GlobalScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["global"] = "global"


class ServerScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["server"] = "server"
    server_id: str

    @field_validator("server_id")
    @classmethod
    def valid_server(cls, value: str) -> str:
        validate_server_name(value)
        return value


class PathsScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["paths"] = "paths"
    server_id: str
    paths: tuple[str, ...] = Field(min_length=1)

    @field_validator("paths")
    @classmethod
    def normalize_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({relative_path(value) for value in values}))


class WorldScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["world"] = "world"
    server_id: str
    selection: RestorationSelection

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        selection = self.selection
        if selection.type not in {
            RestorationType.WORLD,
            RestorationType.DIMENSION,
            RestorationType.REGIONS,
            RestorationType.CHUNKS,
        }:
            raise ValueError("不是有效的世界恢复范围")
        if selection.type is RestorationType.WORLD:
            if selection.region_dir_relpath or selection.regions or selection.chunks:
                raise ValueError("整个世界范围不能同时选择维度、区域或区块")
            return self
        if not selection.region_dir_relpath:
            raise ValueError("请选择维度路径")
        path = relative_path(selection.region_dir_relpath)
        if PurePosixPath(path).name != "region":
            raise ValueError("维度路径必须指向 region 目录")
        if selection.type is RestorationType.REGIONS and not selection.regions:
            raise ValueError("请选择至少一个区域")
        if selection.type is RestorationType.CHUNKS and not selection.chunks:
            raise ValueError("请选择至少一个区块")
        if (selection.regions and selection.type is not RestorationType.REGIONS) or (
            selection.chunks and selection.type is not RestorationType.CHUNKS
        ):
            raise ValueError("选择内容与恢复范围类型不一致")
        object.__setattr__(
            self,
            "selection",
            selection.model_copy(
                update={
                    "region_dir_relpath": path,
                    "regions": sorted(set(selection.regions)),
                    "chunks": sorted(set(selection.chunks)),
                },
                deep=True,
            ),
        )
        return self


SnapshotScope = Annotated[
    GlobalScope | ServerScope | PathsScope | WorldScope, Field(discriminator="kind")
]
scope_adapter = TypeAdapter(SnapshotScope)


def disjoint_paths(paths: Sequence[Path]) -> tuple[Path, ...]:
    selected = set(paths)
    return tuple(
        sorted(
            path
            for path in selected
            if not any(parent in selected for parent in path.parents)
        )
    )


@dataclass(frozen=True)
class ResolvedScope:
    scope: SnapshotScope
    paths: tuple[Path, ...]
    servers: tuple[ServerRef, ...]
    claims: tuple[ResourceClaim, ...]


async def resolve_scope(
    scope: SnapshotScope,
    *,
    root: Path,
    sessions: Callable[[], AbstractAsyncContextManager[AsyncSession]],
) -> ResolvedScope:
    async with sessions() as session:
        if isinstance(scope, GlobalScope):
            names = list(
                await session.scalars(
                    select(Server.server_id)
                    .where(Server.status == ServerStatus.ACTIVE)
                    .order_by(Server.server_id)
                )
            )
        else:
            names = [scope.server_id]
        references = tuple(
            [
                await resolve_server_ref(
                    session,
                    name,
                    servers_root=root,
                    require_exists=not isinstance(scope, GlobalScope),
                )
                for name in names
            ]
        )
    if isinstance(scope, GlobalScope):
        return ResolvedScope(
            scope,
            (await async_fs.resolve(root),),
            references,
            (ResourceClaim(ResourceKind.FILES),),
        )
    reference = references[0]
    if isinstance(scope, ServerScope):
        targets = [reference.project_path]
    elif isinstance(scope, PathsScope):
        targets = [reference.data_path / value for value in scope.paths]
    else:
        targets = await resolve_paths(
            reference.data_path, scope.selection, include_mcc=True, include_missing=True
        )
    claim_paths = (
        await resource_scopes(reference.data_path, targets)
        if isinstance(scope, WorldScope)
        else targets
    )
    claims = await path_claims(
        reference.project_path, claim_paths, server_id=reference.server_id
    )
    try:
        base = (
            reference.project_path
            if isinstance(scope, ServerScope)
            else reference.data_path
        )
        paths = disjoint_paths(
            [await async_fs.resolve_inside(base, target) for target in targets]
        )
    except async_fs.PathOutsideBaseError as error:
        raise HTTPException(status_code=400, detail="目标超出服务器数据目录") from error
    if not paths:
        raise HTTPException(status_code=400, detail="所选范围没有可处理的内容")
    return ResolvedScope(scope, paths, references, claims)
