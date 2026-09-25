"""Canonical filesystem claims shared by file and snapshot applications."""

import posixpath
from collections.abc import Sequence
from pathlib import Path

from fastapi import HTTPException

from ..operations.coordinator import ResourceClaim, ResourceKind
from ..utils import async_fs


async def path_claims(
    base: Path, paths: Sequence[Path], *, server_id: str = "",
    kind: ResourceKind = ResourceKind.FILES,
) -> tuple[ResourceClaim, ...]:
    root = await async_fs.resolve(base)
    claims: set[ResourceClaim] = set()
    for path in paths:
        try:
            resolved = await async_fs.resolve_inside(base, path)
            relative = resolved.relative_to(root)
            claims.add(ResourceClaim(kind, server_id, "" if relative == Path(".") else relative.as_posix()))
            lexical = Path(posixpath.normpath(str(path))).relative_to(Path(posixpath.normpath(str(base))))
            claims.add(ResourceClaim(kind, server_id, "" if lexical == Path(".") else lexical.as_posix()))
        except (async_fs.PathOutsideBaseError, ValueError) as error:
            raise HTTPException(status_code=400, detail="路径越界：目标路径不在文件目录内") from error
    return tuple(sorted(claims))


def require_same_claims(expected: Sequence[ResourceClaim], current: Sequence[ResourceClaim]) -> None:
    if set(expected) != set(current):
        raise HTTPException(status_code=409, detail="文件路径已变化，请刷新后重试")
