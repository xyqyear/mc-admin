from typing import Annotated

from pydantic import ConfigDict, Field

from ..schemas import BaseConfigSchema


class MCMapConfig(BaseConfigSchema):
    """Server map (mcmap) rendering configuration."""

    model_config = ConfigDict(title="地图渲染配置")

    batch_size: Annotated[
        int,
        Field(
            title="单次渲染区域上限",
            description="单次调用 mcmap 时最多渲染的 region 数量。",
            ge=1,
            le=256,
        ),
    ] = 16
    thread_count: Annotated[
        int,
        Field(
            title="渲染线程数",
            description="传递给 mcmap -j 参数的工作线程数量。",
            ge=1,
            le=64,
        ),
    ] = 4
    request_timeout_seconds: Annotated[
        int,
        Field(
            title="瓦片请求超时时间",
            description="瓦片 HTTP 请求等待渲染完成的最长秒数。",
            ge=1,
            le=600,
        ),
    ] = 30
    prune_default_threshold_seconds: Annotated[
        int,
        Field(
            title="区块清理默认阈值",
            description="区块清理页面默认使用的低活跃时间阈值，执行时会转换为 Minecraft tick。",
            ge=0,
            le=60 * 60 * 24 * 365,
        ),
    ] = 30
