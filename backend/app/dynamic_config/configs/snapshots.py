from typing import Annotated

from pydantic import Field

from ..schemas import BaseConfigSchema


class TimeRestrictionConfig(BaseConfigSchema):
    """时间限制配置子模型"""

    enabled: Annotated[bool, Field(description="是否启用快照创建时间限制")] = True
    before_seconds: Annotated[
        int, Field(description="备份时间前多少秒禁止创建快照", ge=0, le=300)
    ] = 30
    after_seconds: Annotated[
        int, Field(description="备份时间后多少秒禁止创建快照", ge=0, le=300)
    ] = 60


class WorldRestoreConfig(BaseConfigSchema):
    """世界恢复(临时目录与预览会话)配置子模型"""

    preview_session_ttl_seconds: Annotated[
        int,
        Field(description="预览会话存活时间(秒);超过此时间未心跳的会话会被清理", ge=60),
    ] = 1800
    preview_janitor_interval_seconds: Annotated[
        int,
        Field(description="预览清理任务的轮询间隔(秒)", ge=10),
    ] = 60
    preview_avg_region_bytes: Annotated[
        int,
        Field(
            description="预览磁盘空间估算中每个 MCA region 的平均字节数",
            ge=1,
        ),
    ] = 8 * 1024 * 1024


class SnapshotsConfig(BaseConfigSchema):
    """快照管理系统配置"""

    # 时间限制配置
    time_restriction: Annotated[
        TimeRestrictionConfig, Field(description="快照创建时间限制配置")
    ] = TimeRestrictionConfig()
    # 世界恢复(临时目录与预览)配置
    world_restore: Annotated[
        WorldRestoreConfig, Field(description="世界恢复临时目录与预览会话配置")
    ] = WorldRestoreConfig()
