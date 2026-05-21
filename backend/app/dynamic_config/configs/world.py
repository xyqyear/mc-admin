from typing import Annotated

from pydantic import Field

from ..schemas import BaseConfigSchema

OVERWORLD_LABEL = "Overworld"
NETHER_LABEL = "Nether"
END_LABEL = "End"

DIMENSION_LABELS = {
    ".": OVERWORLD_LABEL,
    "DIM-1": NETHER_LABEL,
    "DIM1": END_LABEL,
    "dimensions/minecraft/overworld": OVERWORLD_LABEL,
    "dimensions/minecraft/the_nether": NETHER_LABEL,
    "dimensions/minecraft/the_end": END_LABEL,
}


class WorldConfig(BaseConfigSchema):
    """World layout discovery and region manifest configuration."""

    layout_cache_ttl_seconds: Annotated[
        float,
        Field(
            description="每个服务器 data 路径的世界布局发现缓存时间(秒)",
            ge=0,
            le=3600,
        ),
    ] = 5.0
    region_stat_workers: Annotated[
        int,
        Field(
            description="生成区域清单时并发 stat MCA 文件的最大线程数",
            ge=1,
            le=256,
        ),
    ] = 32
    dimension_max_depth_from_world_root: Annotated[
        int,
        Field(
            description="扫描 region 目录时, 维度目录相对世界根目录的最大深度",
            ge=0,
            le=32,
        ),
    ] = 4
    dimension_labels: Annotated[
        dict[str, str],
        Field(
            description="维度显示名称映射; 键为相对世界根目录的维度路径, 根维度使用 '.'"
        ),
    ] = Field(default_factory=lambda: dict(DIMENSION_LABELS))
