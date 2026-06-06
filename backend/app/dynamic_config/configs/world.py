from typing import Annotated

from pydantic import ConfigDict, Field

from ..schemas import BaseConfigSchema

OVERWORLD_LABEL = "主世界"
NETHER_LABEL = "下界"
END_LABEL = "末地"

DIMENSION_LABELS = {
    ".": OVERWORLD_LABEL,
    "DIM-1": NETHER_LABEL,
    "DIM1": END_LABEL,
    "dimensions/minecraft/overworld": OVERWORLD_LABEL,
    "dimensions/minecraft/the_nether": NETHER_LABEL,
    "dimensions/minecraft/the_end": END_LABEL,
}


class WorldConfig(BaseConfigSchema):
    """世界目录识别与区域清单配置。"""

    model_config = ConfigDict(title="世界数据配置")

    region_stat_workers: Annotated[
        int,
        Field(
            title="区域清单扫描线程数",
            description="生成区域清单时并发 stat MCA 文件的最大线程数",
            ge=1,
            le=256,
        ),
    ] = 32
    dimension_max_depth_from_world_root: Annotated[
        int,
        Field(
            title="维度扫描最大深度",
            description="扫描 region 目录时, 维度目录相对世界根目录的最大深度",
            ge=0,
            le=32,
        ),
    ] = 4
    dimension_labels: Annotated[
        dict[str, str],
        Field(
            title="维度显示名称",
            description="维度显示名称映射; 键为相对世界根目录的维度路径, 根维度使用 '.'"
        ),
    ] = Field(default_factory=lambda: dict(DIMENSION_LABELS))
