"""Player system configuration."""

from typing import Annotated

from pydantic import Field

from ..schemas import BaseConfigSchema


class HeartbeatConfig(BaseConfigSchema):
    """Heartbeat and crash recovery configuration."""

    crash_threshold_minutes: Annotated[
        int,
        Field(
            description="系统崩溃检测阈值（分钟）。如果最后心跳超过此时间则认为系统崩溃",
            ge=1,
            le=60,
        ),
    ] = 5

    heartbeat_interval_seconds: Annotated[
        int,
        Field(
            description="心跳更新间隔（秒）",
            ge=10,
        ),
    ] = 60


class RconValidationConfig(BaseConfigSchema):
    """RCON player status validation configuration."""

    validation_interval_seconds: Annotated[
        int,
        Field(
            description="RCON验证间隔（秒）。定期通过RCON查询验证玩家在线状态",
            ge=30,
        ),
    ] = 60


class SkinFetcherConfig(BaseConfigSchema):
    """Player skin fetching configuration."""

    request_timeout_seconds: Annotated[
        int,
        Field(
            description="Mojang API请求超时时间（秒）",
            ge=5,
        ),
    ] = 10

    rate_limit_delay_seconds: Annotated[
        float,
        Field(
            description="请求之间的延迟（秒），用于避免触发Mojang API速率限制",
            ge=0.5,
        ),
    ] = 1.0


class PlayersConfig(BaseConfigSchema):
    """
    Player system configuration.

    Controls heartbeat monitoring, RCON validation, and skin fetching behavior.
    """

    heartbeat: Annotated[
        HeartbeatConfig,
        Field(description="心跳和崩溃恢复配置"),
    ] = HeartbeatConfig()

    rcon_validation: Annotated[
        RconValidationConfig,
        Field(description="RCON玩家状态验证配置"),
    ] = RconValidationConfig()

    skin_fetcher: Annotated[
        SkinFetcherConfig,
        Field(description="玩家皮肤获取配置"),
    ] = SkinFetcherConfig()
