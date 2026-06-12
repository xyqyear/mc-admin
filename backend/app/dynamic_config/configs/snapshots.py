from pathlib import PurePosixPath
from typing import Annotated

from pydantic import ConfigDict, Field, field_validator

from ..schemas import BaseConfigSchema

LEVEL_NAME_TOKEN = "<LEVEL_NAME>"
_GLOB_CHARS = set("*?[]")


class TimeRestrictionConfig(BaseConfigSchema):
    """快照创建时间限制配置。"""

    model_config = ConfigDict(title="快照创建时间限制")

    enabled: Annotated[bool, Field(title="启用时间限制", description="是否启用快照创建时间限制")] = True
    before_seconds: Annotated[
        int, Field(title="备份前禁止秒数", description="备份时间前多少秒禁止创建快照", ge=0, le=300)
    ] = 30
    after_seconds: Annotated[
        int, Field(title="备份后禁止秒数", description="备份时间后多少秒禁止创建快照", ge=0, le=300)
    ] = 60


class WorldRestoreConfig(BaseConfigSchema):
    """世界恢复(临时目录与预览会话)配置子模型"""

    model_config = ConfigDict(title="世界恢复预览配置")

    preview_session_ttl_seconds: Annotated[
        int,
        Field(title="预览会话存活时间", description="预览会话存活时间(秒);超过此时间未心跳的会话会被清理", ge=60),
    ] = 1800
    preview_janitor_interval_seconds: Annotated[
        int,
        Field(title="预览清理轮询间隔", description="预览清理任务的轮询间隔(秒)", ge=10),
    ] = 60
    preview_avg_region_bytes: Annotated[
        int,
        Field(
            title="预览平均 region 字节数",
            description="预览磁盘空间估算中每个 MCA region 的平均字节数",
            ge=1,
        ),
    ] = 8 * 1024 * 1024


class SnapshotsConfig(BaseConfigSchema):
    """快照管理系统配置"""

    model_config = ConfigDict(title="快照管理配置")

    # 时间限制配置
    time_restriction: Annotated[
        TimeRestrictionConfig, Field(title="时间限制", description="快照创建时间限制配置")
    ] = TimeRestrictionConfig()
    # 世界恢复(临时目录与预览)配置
    world_restore: Annotated[
        WorldRestoreConfig, Field(title="世界恢复预览", description="世界恢复临时目录与预览会话配置")
    ] = WorldRestoreConfig()
    # 忽略路径配置
    ignored_paths: Annotated[
        list[str],
        Field(
            title="忽略路径",
            description=(
                "相对于服务器数据目录的路径列表；备份时排除这些路径，恢复时不会覆盖或删除它们。"
                f"支持 {LEVEL_NAME_TOKEN} 占位符（须为完整路径段），展开为 server.properties 中的 level-name。"
                "不支持通配符。"
            ),
        ),
    ] = [".mcmap"]

    @field_validator("ignored_paths")
    @classmethod
    def validate_ignored_paths(cls, v: list[str]) -> list[str]:
        for raw in v:
            path = PurePosixPath(raw)
            if path.is_absolute() or not path.parts:
                raise ValueError(f"忽略路径必须是非空的相对路径: {raw!r}")
            for part in path.parts:
                if part in (".", ".."):
                    raise ValueError(f"忽略路径不允许包含 '.' 或 '..': {raw!r}")
                if _GLOB_CHARS & set(part):
                    raise ValueError(f"忽略路径不支持通配符: {raw!r}")
                if LEVEL_NAME_TOKEN in part and part != LEVEL_NAME_TOKEN:
                    raise ValueError(
                        f"{LEVEL_NAME_TOKEN} 必须作为完整的路径段使用: {raw!r}"
                    )
        return v
