from app.self_check.types import (
    SelfCheckCatalogItem,
    SelfCheckCurrentState,
    SelfCheckRunsResponse,
)


class SelfCheckStatusResponse(SelfCheckRunsResponse):
    catalog: list[SelfCheckCatalogItem]
    current_state: SelfCheckCurrentState | None = None
    retention_runs_keep_days: int
