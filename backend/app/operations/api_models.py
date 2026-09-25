from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.operations.recovery import ResolveAction


class ResourcePublic(BaseModel):
    kind: str
    server_id: str | None
    generation: int | None
    path: str


class RecoveryReferencePublic(BaseModel):
    kind: str
    value: str
    resolved: bool


class OperationPublic(BaseModel):
    operation_id: str
    kind: str
    actor_id: int | None
    origin: str
    name: str
    legacy_id: str | None
    running_intent: bool | None
    resources: list[ResourcePublic]
    state: str
    phase: str
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None
    data_changed: bool
    writers_stopped: bool
    recovery_refs: list[RecoveryReferencePublic]
    failure_code: str | None
    recovery_reason: str | None
    cache_degraded: bool
    resolved_by: int | None
    resolved_at: datetime | None


class ResolveOperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: ResolveAction
    resolve_references: bool = False
