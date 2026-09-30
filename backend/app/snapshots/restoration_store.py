import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.snapshots.restoration_models import Restoration, RestorationStatus
from app.snapshots.selection_models import RestorationSelection

from ..operations.finalization import finalize
from ..operations.journal_types import OperationState
from ..servers.references import ServerRef
from .restoration_models import RestorationType
from .scopes import GlobalScope, ResolvedScope, WorldScope

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def restoration_status(state: OperationState) -> RestorationStatus:
    return {
        OperationState.QUEUED: RestorationStatus.PENDING,
        OperationState.RUNNING: RestorationStatus.RUNNING,
        OperationState.CANCELLING: RestorationStatus.RUNNING,
        OperationState.FINALIZING: RestorationStatus.RUNNING,
        OperationState.SUCCEEDED: RestorationStatus.SUCCEEDED,
        OperationState.CANCELLED: RestorationStatus.CANCELLED,
        OperationState.INTERRUPTED: RestorationStatus.INTERRUPTED,
    }.get(state, RestorationStatus.FAILED)


def restoration_binding_issue(row: Restoration, generation: int | None) -> str | None:
    if row.binding_issue:
        return row.binding_issue
    if row.server_generation is None:
        return "generation_uncertain"
    if row.server_generation != generation:
        return "generation_changed"
    return None


def require_restoration_owner(row: Restoration, reference: ServerRef) -> None:
    if row.server_id != reference.server_id or restoration_binding_issue(
        row, reference.generation
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "restoration_identity_conflict",
                "message": "恢复记录不属于当前服务器实例或历史归属不明确，请核对原服务器及安全快照后手动恢复",
            },
        )


class RestorationStore:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._sessions = session_factory

    async def get(self, restoration_id: str) -> Restoration | None:
        async with self._sessions() as session:
            return await session.scalar(
                select(Restoration).where(Restoration.id == restoration_id)
            )

    async def accept(
        self,
        *,
        restoration_id: str,
        operation_id: str,
        resolved: ResolvedScope,
        source_snapshot_id: str,
        protection_json: str,
        entry_point: str,
        user_id: int,
        rollback_of_id: str | None = None,
    ) -> None:
        scope = resolved.scope
        single = None if isinstance(scope, GlobalScope) else resolved.servers[0]
        kind = (
            scope.selection.type
            if isinstance(scope, WorldScope)
            else RestorationType(scope.kind)
        )

        async def write() -> None:
            async with self._sessions() as session:
                session.add(
                    Restoration(
                        id=restoration_id,
                        operation_id=operation_id,
                        server_id=single.server_id if single else None,
                        server_generation=single.generation if single else None,
                        type=kind,
                        source_snapshot_id=source_snapshot_id,
                        scope_json=json.dumps(
                            {
                                "version": 1,
                                "scope": scope.model_dump(mode="json"),
                                "paths": [str(path) for path in resolved.paths],
                            }
                        ),
                        targets_json=json.dumps(
                            [
                                {
                                    "server_id": ref.server_id,
                                    "generation": ref.generation,
                                }
                                for ref in resolved.servers
                            ]
                        ),
                        protection_json=protection_json,
                        selection_json="{}",
                        entry_point=entry_point,
                        initiated_by_user_id=user_id,
                        status=RestorationStatus.PENDING,
                        rollback_of_id=rollback_of_id,
                        is_rollback=rollback_of_id is not None,
                    )
                )
                await session.commit()

        await finalize(write())

    async def save_protection(self, restoration_id: str, protection_json: str) -> None:
        async def write() -> None:
            async with self._sessions() as session:
                await session.execute(
                    update(Restoration)
                    .where(Restoration.id == restoration_id)
                    .values(protection_json=protection_json)
                )
                await session.commit()

        await finalize(write())

    async def save_safety(
        self,
        restoration_id: str,
        snapshot_id: str,
        absent_paths: list[str],
        absent_parents: list[str],
    ) -> None:
        async def write() -> None:
            async with self._sessions() as session:
                await session.execute(
                    update(Restoration)
                    .where(Restoration.id == restoration_id)
                    .values(
                        safety_snapshot_id=snapshot_id,
                        selection_json=json.dumps(
                            {
                                "absent_paths": absent_paths,
                                "absent_parents": absent_parents,
                            }
                        ),
                        status=RestorationStatus.RUNNING,
                    )
                )
                await session.commit()

        await finalize(write())

    async def finish_operation(
        self, restoration_id: str, state: OperationState
    ) -> None:
        status = restoration_status(state)
        await self.finish(
            restoration_id,
            status,
            None
            if status is RestorationStatus.SUCCEEDED
            else {
                RestorationStatus.CANCELLED: "操作已取消，已写入的内容不会自动回滚",
                RestorationStatus.INTERRUPTED: "操作已中断，请检查恢复记录和写入状态",
            }.get(status, "操作未完成，请查看任务详情"),
        )

    async def insert(
        self,
        *,
        restoration_id: str,
        reference: ServerRef,
        selection: RestorationSelection,
        source_snapshot_id: str,
        safety_snapshot_id: str | None,
        is_rollback: bool,
        user_id: int | None,
        absent_dirs: list[str],
        world_roots: list[str] | None = None,
        rollback_of_id: str | None = None,
        operation_id: str | None = None,
    ) -> None:
        async with self._sessions() as session:
            session.add(
                Restoration(
                    id=restoration_id,
                    server_id=reference.server_id,
                    server_generation=reference.generation,
                    scope_json=json.dumps(
                        {
                            "version": 1,
                            "scope": {
                                "kind": "world",
                                "server_id": reference.server_id,
                                "selection": selection.model_dump(mode="json"),
                            },
                        }
                    ),
                    targets_json=json.dumps(
                        [
                            {
                                "server_id": reference.server_id,
                                "generation": reference.generation,
                            }
                        ]
                    ),
                    entry_point="world",
                    rollback_of_id=rollback_of_id,
                    operation_id=operation_id,
                    type=selection.type,
                    source_snapshot_id=source_snapshot_id,
                    safety_snapshot_id=safety_snapshot_id,
                    selection_json=json.dumps(
                        {
                            **selection.model_dump(mode="json"),
                            "absent_directories": absent_dirs,
                            "world_roots": world_roots,
                        }
                    ),
                    is_rollback=is_rollback,
                    initiated_by_user_id=user_id,
                )
            )
            await session.commit()

    async def finish(
        self, restoration_id: str, status: RestorationStatus, error_message: str | None
    ) -> None:
        async with self._sessions() as session:
            await session.execute(
                update(Restoration)
                .where(Restoration.id == restoration_id)
                .values(
                    status=status,
                    finished_at=datetime.now(UTC),
                    error_message=error_message,
                )
            )
            await session.commit()

    async def interrupt_running(self) -> int:
        async with self._sessions() as session:
            result = await session.execute(
                update(Restoration)
                .where(
                    Restoration.status.in_(
                        [RestorationStatus.PENDING, RestorationStatus.RUNNING]
                    ),
                )
                .values(
                    status=RestorationStatus.INTERRUPTED,
                    error_message="server restarted before completion",
                    finished_at=datetime.now(UTC),
                )
            )
            await session.commit()
            return int(getattr(result, "rowcount", 0) or 0)
