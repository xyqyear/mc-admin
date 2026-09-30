from pydantic import BaseModel

from app.snapshots.selection_models import RestorationSelection


class DimensionInfoResponse(BaseModel):
    region_dir: str
    entities_dir: str | None = None
    poi_dir: str | None = None


class WorldRootResponse(BaseModel):
    name: str
    path: str
    dimensions: list[DimensionInfoResponse]


class WorldLayoutResponse(BaseModel):
    world_roots: list[WorldRootResponse]


class DimensionLabelsResponse(BaseModel):
    dimension_labels: dict[str, str]


class PreviewRequest(BaseModel):
    source_snapshot_id: str
    selection: RestorationSelection
