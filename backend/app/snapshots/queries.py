import json

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import and_, exists, func, or_, select

from ..operations.journal_types import OperationState
from ..operations.models import OperationJournalEntry
from ..servers.models import Server, ServerStatus
from .api_models import (
    ActiveRestoration,
    ActiveRestorationsResponse,
    ListRestorationsResponse,
    RestorationResponse,
)
from .restoration_models import Restoration, RestorationStatus
from .restoration_store import (
    SessionFactory,
    restoration_binding_issue,
    restoration_status,
)
from .scopes import SnapshotScope, scope_adapter
from .service import SnapshotService


def _scope(row: Restoration) -> SnapshotScope | None:
    try:
        return scope_adapter.validate_python(json.loads(row.scope_json or "{}")["scope"])
    except (KeyError, ValueError, ValidationError):
        return None


def _query(
    server_id: str | None,
    statuses: tuple[RestorationStatus, ...] = (),
    kind: str | None = None,
    entry_point: str | None = None,
):
    query = select(Restoration).outerjoin(
        OperationJournalEntry,
        Restoration.operation_id == OperationJournalEntry.operation_id,
    )
    if server_id is not None:
        targets = func.json_each(Restoration.targets_json).table_valued("value")
        query = query.where(or_(
            Restoration.server_id == server_id,
            exists(select(1).select_from(targets).where(
                func.json_extract(targets.c.value, "$.server_id") == server_id
            )),
        ))
    if statuses:
        query = query.where(or_(
            OperationJournalEntry.state.in_([
                state.value for state in OperationState
                if restoration_status(state) in statuses
            ]),
            and_(OperationJournalEntry.operation_id.is_(None), Restoration.status.in_(statuses)),
        ))
    if kind is not None:
        query = query.where(func.json_extract(Restoration.scope_json, "$.scope.kind") == kind)
    if entry_point is not None:
        query = query.where(Restoration.entry_point == entry_point)
    return query


class RestorationQueries:
    def __init__(self, sessions: SessionFactory, snapshots: SnapshotService | None = None) -> None:
        self._sessions = sessions
        self._snapshots = snapshots

    async def history(
        self, server_id: str | None, limit: int, offset: int,
        *, kind: str | None = None, status: RestorationStatus | None = None,
        entry_point: str | None = None,
    ) -> ListRestorationsResponse:
        query = _query(server_id, (status,) if status else (), kind, entry_point)
        async with self._sessions() as session:
            total = await session.scalar(select(func.count()).select_from(query.subquery()))
            rows = list(
                await session.scalars(
                    query.order_by(Restoration.started_at.desc(), Restoration.id)
                    .limit(limit)
                    .offset(offset)
                )
            )
        return ListRestorationsResponse(
            restorations=await self._project(rows), total=total or 0
        )

    async def active(
        self, server_id: str | None, limit: int, offset: int
    ) -> ActiveRestorationsResponse:
        query = _query(server_id, (RestorationStatus.PENDING, RestorationStatus.RUNNING)).where(
            OperationJournalEntry.operation_id.is_not(None)
        )
        async with self._sessions() as session:
            total = await session.scalar(select(func.count()).select_from(query.subquery()))
            rows = (await session.execute(
                query.add_columns(OperationJournalEntry.state)
                .order_by(Restoration.started_at.desc(), Restoration.id)
                .limit(limit).offset(offset)
            )).all()
        return ActiveRestorationsResponse(
            total=total or 0,
            restorations=[ActiveRestoration(
                id=row.id, operation_id=row.operation_id,
                scope=_scope(row), status=restoration_status(OperationState(state)),
            ) for row, state in rows if row.operation_id is not None],
        )

    async def get(self, restoration_id: str) -> RestorationResponse:
        async with self._sessions() as session:
            row = await session.get(Restoration, restoration_id)
        if row is None:
            raise HTTPException(status_code=404, detail="恢复记录不存在")
        return (await self._project([row]))[0]

    async def _project(self, rows: list[Restoration]) -> list[RestorationResponse]:
        if not rows:
            return []
        if self._snapshots is None:
            raise HTTPException(status_code=503, detail="尚未配置快照仓库，无法核对回滚状态")
        snapshots = {snapshot.id for snapshot in await self._snapshots.list_snapshots()}
        async with self._sessions() as session:
            servers = {
                name: generation
                for name, generation in await session.execute(
                    select(Server.server_id, Server.id).where(
                        Server.status == ServerStatus.ACTIVE
                    )
                )
            }
            operation_ids = [row.operation_id for row in rows if row.operation_id]
            operations = {
                record.operation_id: record
                for record in await session.scalars(
                    select(OperationJournalEntry).where(
                        OperationJournalEntry.operation_id.in_(operation_ids)
                    )
                )
            }
        results = []
        for row in rows:
            operation = operations.get(row.operation_id) if row.operation_id else None
            status = (
                restoration_status(OperationState(operation.state))
                if operation
                else row.status
            )
            scope = _scope(row)
            source_exists = row.source_snapshot_id in snapshots
            safety_exists = (
                row.safety_snapshot_id is not None
                and row.safety_snapshot_id in snapshots
            )
            targets = json.loads(row.targets_json or "[]")
            binding_issue = (
                restoration_binding_issue(row, servers.get(row.server_id))
                if row.server_id
                else row.binding_issue
            )
            reason = None
            if status in {RestorationStatus.PENDING, RestorationStatus.RUNNING}:
                reason = "恢复任务尚未结束"
            elif operation is not None and (
                not operation.writers_stopped or operation.blocked_reason
            ):
                reason = "请先在操作历史中完成写入和恢复状态核对"
            elif not safety_exists:
                reason = "安全快照不存在，可能已按保留策略删除"
            elif (
                scope is None
                or binding_issue
                or any(
                    target.get("generation") is None
                    or servers.get(target["server_id"]) != target["generation"]
                    for target in targets
                )
            ):
                reason = "历史归属或范围不明确，无法写入当前服务器实例"
            results.append(
                RestorationResponse(
                    id=row.id,
                    operation_id=row.operation_id,
                    server_id=row.server_id,
                    server_generation=row.server_generation,
                    binding_issue=binding_issue,
                    entry_point=row.entry_point,
                    initiated_by_user_id=row.initiated_by_user_id,
                    scope=scope,
                    targets=targets,
                    source_snapshot_id=row.source_snapshot_id,
                    safety_snapshot_id=row.safety_snapshot_id,
                    source_snapshot_exists=source_exists,
                    safety_snapshot_exists=safety_exists,
                    rollback_available=reason is None,
                    rollback_unavailable_reason=reason,
                    rollback_of_id=row.rollback_of_id,
                    is_rollback=row.is_rollback,
                    started_at=row.started_at,
                    finished_at=operation.ended_at if operation else row.finished_at,
                    status=status,
                    error_message=row.error_message,
                )
            )
        return results
