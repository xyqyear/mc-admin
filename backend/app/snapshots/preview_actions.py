import json
from pathlib import Path

import aiofiles
from fastapi import HTTPException

from .preview_models import PreviewAction, PreviewActions

MAX_ACTION_BYTES = 64 * 1024 * 1024
MAX_LINE_BYTES = 32 * 1024


async def read_actions(path: Path, cursor: int, limit: int) -> PreviewActions:
    async with aiofiles.open(path, "rb") as stream:
        if cursor:
            await stream.seek(cursor - 1)
            if await stream.read(1) != b"\n":
                raise HTTPException(status_code=400, detail="预览分页位置无效")
        actions = []
        for _ in range(limit):
            line = await stream.readline(MAX_LINE_BYTES + 1)
            if not line:
                return PreviewActions(actions=actions)
            if len(line) > MAX_LINE_BYTES:
                raise HTTPException(status_code=409, detail="预览明细无效，请重新准备")
            actions.append(PreviewAction.model_validate(json.loads(line)))
        position = await stream.tell()
        more = await stream.read(1)
    return PreviewActions(actions=actions, next_cursor=position if more else None)
