from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .preparation import PreparedSnapshot
from .scopes import SnapshotScope


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: SnapshotScope
    source_snapshot_id: str = Field(pattern="^[0-9a-f]{64}$")


class PreviewResult(BaseModel):
    preview_id: str
    kind: Literal["files", "map"]
    preview_summary: str
    updated: int = 0
    deleted: int = 0
    restored: int = 0
    skipped_paths: list[str] = []
    skipped_count: int = 0
    notice: str = "预览反映准备时的状态；在线文件仍可能被外部程序修改，恢复前会另存当时的安全快照。"


class PreviewAction(BaseModel):
    action: Literal["updated", "deleted", "restored"]
    item: str
    size: int | None = None


class PreviewActions(BaseModel):
    actions: list[PreviewAction]
    next_cursor: int | None = None


@dataclass(frozen=True)
class PreviewBinding:
    source_id: str
    prepared: PreparedSnapshot
    target_version: str
