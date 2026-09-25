import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.world.models import Restoration, RestorationStatus
from app.world.schemas import RestorationSelection

from ..servers.references import ServerRef

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def restoration_binding_issue(row: Restoration, generation: int | None) -> str | None:
    if row.binding_issue:
        return row.binding_issue
    if row.server_generation is None:
        return "generation_uncertain"
    if row.server_generation != generation:
        return "generation_changed"
    return None


def require_restoration_owner(row: Restoration, reference: ServerRef) -> None:
    if row.server_id != reference.server_id or restoration_binding_issue(row, reference.generation):
        raise HTTPException(status_code=409, detail={
            "code": "restoration_identity_conflict",
            "message": "恢复记录不属于当前服务器实例或历史归属不明确，请核对原服务器及安全快照后手动恢复",
        })


class RestorationStore:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._sessions = session_factory

    async def get(self, restoration_id: str) -> Restoration | None:
        async with self._sessions() as session:
            return await session.scalar(select(Restoration).where(Restoration.id == restoration_id))

    async def insert(
        self, *, restoration_id: str, reference: ServerRef,
        selection: RestorationSelection, source_snapshot_id: str,
        safety_snapshot_id: str | None, is_rollback: bool,
        user_id: int | None, absent_dirs: list[str],
        world_roots: list[str] | None = None,
    ) -> None:
        async with self._sessions() as session:
            session.add(Restoration(
                id=restoration_id, server_id=reference.server_id,
                server_generation=reference.generation,
                type=selection.type, source_snapshot_id=source_snapshot_id,
                safety_snapshot_id=safety_snapshot_id,
                selection_json=json.dumps({**selection.model_dump(mode="json"), "absent_directories": absent_dirs,
                                           "world_roots": world_roots}),
                is_rollback=is_rollback, initiated_by_user_id=user_id,
            ))
            await session.commit()

    async def finish(self, restoration_id: str, status: RestorationStatus, error_message: str | None) -> None:
        async with self._sessions() as session:
            await session.execute(update(Restoration).where(Restoration.id == restoration_id).values(
                status=status, finished_at=datetime.now(UTC), error_message=error_message,
            ))
            await session.commit()

    async def interrupt_running(self) -> int:
        async with self._sessions() as session:
            result = await session.execute(update(Restoration).where(
                Restoration.status == RestorationStatus.RUNNING,
            ).values(status=RestorationStatus.INTERRUPTED,
                     error_message="server restarted before completion", finished_at=datetime.now(UTC)))
            await session.commit()
            return int(getattr(result, "rowcount", 0) or 0)
