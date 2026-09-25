from pydantic import BaseModel
from pydantic import Field as PydanticField

from app.world.models import RestorationType


class RestorationSelection(BaseModel):
    """What is being snapshotted/restored. ``chunks`` holds absolute chunk coords."""

    type: RestorationType
    # Required for DIMENSION/REGIONS/CHUNKS; ignored for WORLD. Path relative
    # to the server's data/ dir (e.g. "world/region"); the world root dir name
    # is its prefix, so it uniquely identifies a dimension across roots.
    region_dir_relpath: str | None = None
    regions: list[tuple[int, int]] = PydanticField(default_factory=list)
    chunks: list[tuple[int, int]] = PydanticField(default_factory=list)
