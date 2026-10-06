"""Bounded recursive file enumeration for browser-owned local exports."""

import base64
import binascii
import json
import posixpath
from dataclasses import asdict
from typing import Literal, cast

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

from ..servers.references import ServerRef
from ..utils import async_fs
from .api_models import (
    DownloadManifestEntry,
    DownloadManifestError,
    DownloadManifestRequest,
    DownloadManifestResponse,
)
from .paths import normalize_selected_paths


class DirectoryCursor(BaseModel):
    path: str
    offset: int = Field(ge=0)
    stamp: tuple[int, int, int]


class PageCursor(BaseModel):
    root_index: int = Field(ge=0)
    directories: list[DirectoryCursor]


async def download_manifest(reference: ServerRef, request: DownloadManifestRequest) -> DownloadManifestResponse:
    roots = await normalize_selected_paths(reference.data_path, request.paths)
    identity = [reference.server_id, reference.generation, str(reference.data_path), list(roots)]
    state: async_fs.TreePageCursor | None = None
    if request.cursor is not None:
        try:
            cursor = json.loads(base64.b64decode(request.cursor, altchars=b"-_", validate=True))
        except (ValueError, binascii.Error, UnicodeDecodeError) as error:
            raise HTTPException(status_code=400, detail="下载清单游标无效，请重新开始下载") from error
        if not isinstance(cursor, dict):
            raise HTTPException(status_code=400, detail="下载清单游标无效，请重新开始下载")
        if cursor.get("identity") != identity:
            raise HTTPException(status_code=409, detail="下载范围或服务器实例已变化，请重新开始下载")
        try:
            page_cursor = PageCursor.model_validate(cursor.get("state"))
        except ValidationError as error:
            raise HTTPException(status_code=400, detail="下载清单游标无效，请重新开始下载") from error
        if page_cursor.root_index > len(roots) or (page_cursor.directories and page_cursor.root_index == 0):
            raise HTTPException(status_code=400, detail="下载清单游标无效，请重新开始下载")
        parent = roots[page_cursor.root_index - 1] if page_cursor.root_index else ""
        for index, directory in enumerate(page_cursor.directories):
            normalized = posixpath.normpath(directory.path)
            if normalized != (directory.path or ".") or directory.path.startswith("/"):
                raise HTTPException(status_code=400, detail="下载清单游标无效，请重新开始下载")
            if (index == 0 and directory.path != parent) or (index and not directory.path.startswith(parent + "/" if parent else "")):
                raise HTTPException(status_code=400, detail="下载清单游标无效，请重新开始下载")
            parent = directory.path
        state = async_fs.TreePageCursor(page_cursor.root_index, [async_fs.TreeDirectoryCursor(item.path, item.offset, item.stamp) for item in page_cursor.directories])
    try:
        page, next_state = await async_fs.tree_page(reference.data_path, roots, cursor=state, limit=request.limit)
    except (async_fs.TreeChangedError, OSError) as error:
        raise HTTPException(status_code=409, detail="下载目录结构已变化，请重新开始下载") from error
    next_cursor = None
    if next_state is not None:
        next_cursor = base64.urlsafe_b64encode(json.dumps({"identity": identity, "state": asdict(next_state)}).encode()).decode()
    return DownloadManifestResponse(
        server_generation=reference.generation,
        entries=[DownloadManifestEntry(path=path, type=cast(Literal["file", "directory"], kind), size=size) for path, kind, size, error in page if error is None],
        errors=[DownloadManifestError(path=path, message=error) for path, _, _, error in page if error is not None],
        next_cursor=next_cursor,
    )
