"""Player system configuration."""

from typing import Annotated

from pydantic import ConfigDict, Field

from ..schemas import BaseConfigSchema


class HeartbeatConfig(BaseConfigSchema):
    """Heartbeat and crash recovery configuration."""

    model_config = ConfigDict(title="心跳与崩溃恢复配置")

    crash_threshold_minutes: Annotated[
        int,
        Field(
            title="崩溃检测阈值",
            description="系统崩溃检测阈值（分钟）。如果最后心跳超过此时间则认为系统崩溃",
            ge=1,
            le=60,
        ),
    ] = 5

    heartbeat_interval_seconds: Annotated[
        int,
        Field(
            title="心跳更新间隔",
            description="心跳更新间隔（秒）",
            ge=10,
        ),
    ] = 60


class RconValidationConfig(BaseConfigSchema):
    """RCON 玩家状态验证配置。"""

    model_config = ConfigDict(title="RCON 玩家状态验证配置")

    validation_interval_seconds: Annotated[
        int,
        Field(
            title="RCON 验证间隔",
            description="RCON验证间隔（秒）。定期通过RCON查询验证玩家在线状态",
            ge=30,
        ),
    ] = 60


class SkinFetcherConfig(BaseConfigSchema):
    """玩家皮肤获取配置。"""

    model_config = ConfigDict(title="玩家皮肤获取配置")

    request_timeout_seconds: Annotated[
        int,
        Field(
            title="Mojang API 请求超时",
            description="Mojang API请求超时时间（秒）",
            ge=5,
        ),
    ] = 10


class QueryConfig(BaseConfigSchema):
    """Query 协议玩家列表配置。"""

    model_config = ConfigDict(title="Query 协议配置")

    query_command: Annotated[
        str,
        Field(
            title="Query 命令模板",
            description="Query协议获取玩家列表的bash命令模板，其中25565会被替换为实际的query端口"
        ),
    ] = r'exec 3<>/dev/udp/localhost/25565 && printf "\xfe\xfd\x09\x00\x00\x00\x01" >&3 && c=$(dd bs=1024 count=1 <&3 2>/dev/null | tail -c +6 | tr -d "\0") && b1=$(printf "%02x" $((c>>24&255))) && b2=$(printf "%02x" $((c>>16&255))) && b3=$(printf "%02x" $((c>>8&255))) && b4=$(printf "%02x" $((c&255))) && printf "\xfe\xfd\x00\x00\x00\x00\x01\x$b1\x$b2\x$b3\x$b4\x00\x00\x00\x00" >&3 && dd bs=4096 count=1 <&3 2>/dev/null | tail -c +17 | tr "\0" "\n" | awk "/player_/{f=1;next}f&&NF" && exec 3>&-'

    timeout: Annotated[
        float,
        Field(title="Query 请求超时", description="使用Query协议获取玩家列表的超时"),
    ] = 0.25


class PlayersConfig(BaseConfigSchema):
    """玩家系统配置。"""

    model_config = ConfigDict(title="玩家系统配置")

    heartbeat: Annotated[
        HeartbeatConfig,
        Field(title="心跳和崩溃恢复", description="心跳和崩溃恢复配置"),
    ] = HeartbeatConfig()

    rcon_validation: Annotated[
        RconValidationConfig,
        Field(title="RCON 玩家状态验证", description="RCON玩家状态验证配置"),
    ] = RconValidationConfig()

    skin_fetcher: Annotated[
        SkinFetcherConfig,
        Field(title="玩家皮肤获取", description="玩家皮肤获取配置"),
    ] = SkinFetcherConfig()

    query: Annotated[
        QueryConfig,
        Field(title="Query 协议", description="Query协议配置"),
    ] = QueryConfig()

    ignored_name_prefixes: Annotated[
        list[str],
        Field(
            title="忽略的玩家名前缀",
            description="不写入玩家数据库的玩家名前缀列表，忽略大小写，默认包含 bot_",
        ),
    ] = ["bot_"]
