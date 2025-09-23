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


class SnapshotsConfig(BaseConfigSchema):
    """快照管理系统配置"""

    # 时间限制配置
    time_restriction: Annotated[
        TimeRestrictionConfig, Field(description="快照创建时间限制配置")
    ] = TimeRestrictionConfig()

    # 恢复安全检查配置
    restore_safety_max_age_seconds: Annotated[
        int, Field(description="恢复安全检查要求的最近快照最大年龄（秒）", ge=30, le=3600)
    ] = 60