from pydantic import BaseModel

from app.background_tasks.api_models import BackgroundTaskResponse
from app.chunk_prune.models import ChunkPrunePreviewState


class ChunkPruneApplyRequest(BaseModel):
    preview_task_id: str


class ChunkPruneStateResponse(BaseModel):
    preview_task: BackgroundTaskResponse | None
    apply_task: BackgroundTaskResponse | None
    preview: ChunkPrunePreviewState | None = None
