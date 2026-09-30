from pydantic import BaseModel, field_validator
from pydantic import Field as PydanticField

from app.snapshots.restoration_models import RestorationType


class RestorationSelection(BaseModel):
    """What is being snapshotted/restored. ``chunks`` holds absolute chunk coords."""

    type: RestorationType
    # Required for DIMENSION/REGIONS/CHUNKS; ignored for WORLD. Path relative
    # to the server's data/ dir (e.g. "world/region"); the world root dir name
    # is its prefix, so it uniquely identifies a dimension across roots.
    region_dir_relpath: str | None = None
    regions: list[tuple[int, int]] = PydanticField(default_factory=list)
    chunks: list[tuple[int, int]] = PydanticField(default_factory=list)

    @field_validator("type")
    @classmethod
    def world_type(cls, value: RestorationType) -> RestorationType:
        if value not in {
            RestorationType.WORLD, RestorationType.DIMENSION,
            RestorationType.REGIONS, RestorationType.CHUNKS,
        }:
            raise ValueError("不是有效的世界选择类型")
        return value
