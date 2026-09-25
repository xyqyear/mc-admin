from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.models import UserRole
from app.auth.schemas import UserPublic
from app.operations.api_models import (
    OperationPublic,
    RecoveryReferencePublic,
    ResolveOperationRequest,
    ResourcePublic,
)

from ..dependencies import RequireRole, get_current_user
from ..operation_admission import get_server_write_admission
from ..operations.journal import OperationJournal
from ..operations.journal_types import OperationRecord
from ..operations.recovery import REASONS, RecoveryService
from ..runtime_resources import current_runtime

router = APIRouter(prefix="/operations", tags=["operations"])


def _journal() -> OperationJournal:
    journal = current_runtime().journal
    if journal is None:
        raise HTTPException(status_code=503, detail="操作历史尚未初始化")
    return journal


def _recovery() -> RecoveryService:
    recovery = current_runtime().resources.get("operation_recovery")
    if not isinstance(recovery, RecoveryService):
        raise HTTPException(status_code=503, detail="操作恢复尚未初始化")
    return recovery


def _public(record: OperationRecord) -> OperationPublic:
    return OperationPublic(
        operation_id=record.operation_id, kind=record.kind, actor_id=record.actor_id,
        origin=record.origin, name=record.name, legacy_id=record.legacy_id,
        running_intent=record.running_intent,
        resources=[ResourcePublic(**asdict(resource)) for resource in record.resources],
        state=record.state.value, phase=record.phase, created_at=record.created_at,
        updated_at=record.updated_at, ended_at=record.ended_at, data_changed=record.data_changed,
        writers_stopped=record.writers_stopped,
        recovery_refs=[RecoveryReferencePublic(**asdict(reference)) for reference in record.recovery_refs],
        failure_code=record.failure_code,
        recovery_reason=REASONS.get(record.blocked_reason, "操作需要人工核对") if record.blocked_reason else None,
        cache_degraded=record.cache_degraded, resolved_by=record.resolved_by, resolved_at=record.resolved_at,
    )


@router.get("", response_model=list[OperationPublic])
async def list_operations(
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    _: UserPublic = Depends(get_current_user),
):
    return [_public(record) for record in await _journal().list(limit=limit, offset=offset)]


@router.get("/{operation_id}", response_model=OperationPublic)
async def get_operation(operation_id: str, _: UserPublic = Depends(get_current_user)):
    record = await _journal().get(operation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="操作记录不存在")
    return _public(record)


@router.post("/{operation_id}/resolve", response_model=OperationPublic)
async def resolve_operation(
    operation_id: str, body: ResolveOperationRequest,
    user: UserPublic = Depends(RequireRole(UserRole.OWNER)),
):
    recovery = _recovery()
    record = await recovery.resolve(
        operation_id, actor_id=user.id, action=body.action,
        resolve_references=body.resolve_references,
    )
    await recovery.apply_blocks(get_server_write_admission())
    return _public(record)
