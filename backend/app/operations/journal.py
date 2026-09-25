import asyncio
import builtins
import json
import re
from collections.abc import AsyncGenerator, Awaitable, Callable, Coroutine, Sequence
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from functools import wraps
from pathlib import PurePosixPath
from typing import Any, Concatenate

from anyio.lowlevel import checkpoint_if_cancelled
from fastapi import HTTPException
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..errors import PublicOperationError
from .finalization import finalize
from .journal_types import (
    TERMINAL_STATES,
    JournalLimits,
    OperationRecord,
    OperationSpec,
    OperationState,
    ProcessIdentity,
    RecoveryReference,
    ResourceReference,
)
from .models import OperationJournalEntry

_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,64}\Z")


async def _complete_database_call[T](awaitable: Awaitable[T]) -> T:
    try:
        result = await finalize(awaitable)
    except Exception as error:
        try:
            await checkpoint_if_cancelled()
        except asyncio.CancelledError as cancelled:
            raise cancelled from error
        raise
    await checkpoint_if_cancelled()
    return result


def _complete_read[**P, T](method: Callable[P, Awaitable[T]]) -> Callable[P, Coroutine[Any, Any, T]]:
    @wraps(method)
    async def completed(*args: P.args, **kwargs: P.kwargs) -> T:
        await checkpoint_if_cancelled()
        return await _complete_database_call(method(*args, **kwargs))
    return completed


def _complete_write[**P, T](
    method: Callable[Concatenate["OperationJournal", P], Awaitable[T]],
) -> Callable[Concatenate["OperationJournal", P], Coroutine[Any, Any, T]]:
    @wraps(method)
    async def completed(self: "OperationJournal", /, *args: P.args, **kwargs: P.kwargs) -> T:
        async with self._lock:
            await checkpoint_if_cancelled()
            return await _complete_database_call(method(self, *args, **kwargs))
    return completed


class JournalCapacityError(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=503, detail="操作记录已达到容量上限，请先处理未完成操作或恢复事项")


class InvalidOperationTransition(PublicOperationError):
    def __init__(self) -> None:
        super().__init__("操作状态已变化，或所属写入尚未结束，请重新获取状态")


def _token(value: str, *, maximum: int = 64) -> str:
    if len(value) > maximum or not _TOKEN.fullmatch(value):
        raise ValueError("Operation metadata requires a bounded identifier")
    return value


def _bounded_text(value: str, maximum: int) -> str:
    if len(value.encode()) > maximum or any(ord(character) < 32 for character in value):
        raise ValueError("Operation metadata contains invalid or oversized text")
    return value


def _resources(values: Sequence[ResourceReference], maximum: int) -> str:
    if len(values) > maximum:
        raise JournalCapacityError()
    if not values or len(set(values)) != len(values):
        raise ValueError("Operation resources must be nonempty, unique and bounded")
    for resource in values:
        _token(resource.kind, maximum=40)
        if (resource.server_id is None) != (resource.generation is None):
            raise ValueError("Server resources require their exact generation")
        if resource.server_id is not None:
            _bounded_text(resource.server_id, 4000)
            if not resource.server_id or resource.generation is None or resource.generation <= 0:
                raise ValueError("Invalid server generation")
        _bounded_text(resource.path, 4096)
        path = PurePosixPath(resource.path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Operation resource paths must be confined relative paths")
    return _encode(values)


def _encode(values: Sequence[Any]) -> str:
    payload = json.dumps([asdict(value) for value in values], ensure_ascii=False, separators=(",", ":"))
    if len(payload.encode()) > 65_536:
        raise JournalCapacityError()
    return payload


def _record(row: OperationJournalEntry) -> OperationRecord:
    return OperationRecord(
        operation_id=row.operation_id, kind=row.kind, actor_id=row.actor_id,
        origin=row.origin, name=row.name, legacy_id=row.legacy_id,
        running_intent=row.running_intent, configuration_version=row.configuration_version,
        resources=tuple(ResourceReference(**value) for value in json.loads(row.resources_json)),
        state=OperationState(row.state), phase=row.phase,
        created_at=row.created_at, updated_at=row.updated_at, ended_at=row.ended_at,
        data_changed=row.data_changed, writers_stopped=row.writers_stopped,
        ownership_known=row.ownership_known,
        processes=tuple(ProcessIdentity(**value) for value in json.loads(row.processes_json)),
        recovery_refs=tuple(RecoveryReference(**value) for value in json.loads(row.recovery_refs_json)),
        failure_code=row.failure_code, blocked_reason=row.blocked_reason,
        cache_degraded=row.cache_degraded, resolved_by=row.resolved_by, resolved_at=row.resolved_at,
    )


class OperationJournal:
    """Finish short database calls and close their cursors before propagating cancellation."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], *,
        limits: JournalLimits | None = None, clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.limits = limits or JournalLimits()
        if min(self.limits.max_records, self.limits.max_resources, self.limits.max_recovery_refs, self.limits.max_processes) < 1:
            raise ValueError("Journal capacity limits must be positive")
        if self.limits.terminal_max_age.total_seconds() <= 0:
            raise ValueError("Journal retention age must be positive")
        self.clock = clock or (lambda: datetime.now(UTC))
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def _write(self, *, committed: Callable[[], None] | None = None) -> AsyncGenerator[AsyncSession]:
        async with self.session_factory() as session:
            async with session.begin():
                if session.get_bind().dialect.name == "sqlite":
                    await session.execute(text("BEGIN IMMEDIATE"))
                yield session
            if committed is not None:
                committed()

    async def _row(self, session: AsyncSession, operation_id: str) -> OperationJournalEntry:
        row = await session.get(OperationJournalEntry, operation_id)
        if row is None:
            raise KeyError(operation_id)
        return row

    def _active(self, row: OperationJournalEntry) -> None:
        if OperationState(row.state) in TERMINAL_STATES:
            raise InvalidOperationTransition()

    async def accept(
        self, spec: OperationSpec, *, on_accepted: Callable[[OperationRecord], None] | None = None,
    ) -> OperationRecord:
        async with self._lock:
            await checkpoint_if_cancelled()
            return await _complete_database_call(self._accept(spec, on_accepted=on_accepted))

    async def _accept(
        self, spec: OperationSpec, *, on_accepted: Callable[[OperationRecord], None] | None,
    ) -> OperationRecord:
        _token(spec.operation_id)
        _token(spec.kind, maximum=40)
        _bounded_text(spec.name, 200)
        if spec.origin not in {"task", "cron", "request", "system"}:
            raise ValueError("Invalid operation execution origin")
        if spec.legacy_id is not None:
            _token(spec.legacy_id)
        if spec.configuration_version is not None:
            _token(spec.configuration_version)
        resource_json = _resources(spec.resources, self.limits.max_resources)
        accepted: OperationRecord | None = None

        def committed() -> None:
            if on_accepted is not None:
                assert accepted is not None
                on_accepted(accepted)

        async with self._write(committed=committed) as session:
            await self._prune(session, reserve=1)
            count = await session.scalar(select(func.count()).select_from(OperationJournalEntry))
            if count is not None and count >= self.limits.max_records:
                raise JournalCapacityError()
            now = self.clock()
            row = OperationJournalEntry(
                operation_id=spec.operation_id, kind=spec.kind, actor_id=spec.actor_id,
                origin=spec.origin, name=spec.name, legacy_id=spec.legacy_id,
                running_intent=spec.running_intent, configuration_version=spec.configuration_version,
                resources_json=resource_json, state=OperationState.QUEUED.value, phase="accepted",
                created_at=now, updated_at=now, ended_at=None, data_changed=False,
                writers_stopped=True, ownership_known=True, processes_json="[]", recovery_refs_json="[]",
                has_recovery_refs=False, failure_code=None, blocked_reason=None,
                cache_degraded=False, resolved_by=None, resolved_at=None,
            )
            session.add(row)
            await session.flush()
            accepted = _record(row)
            return accepted

    @_complete_write
    async def start(self, operation_id: str) -> OperationRecord:
        async with self._write() as session:
            row = await self._row(session, operation_id)
            if row.state != OperationState.QUEUED:
                raise InvalidOperationTransition()
            row.state, row.phase = OperationState.RUNNING.value, "started"
            row.writers_stopped = False
            row.updated_at = self.clock()
            return _record(row)

    @_complete_write
    async def phase(
        self, operation_id: str, phase: str, *, changed: bool = False,
        state: OperationState | None = None,
        recovery_refs: Sequence[RecoveryReference] = (),
    ) -> OperationRecord:
        _token(phase)
        if state is not None and state not in {OperationState.RUNNING, OperationState.CANCELLING, OperationState.FINALIZING}:
            raise InvalidOperationTransition()
        async with self._write() as session:
            row = await self._row(session, operation_id)
            self._active(row)
            row.phase = phase
            row.data_changed = row.data_changed or changed
            if state is not None:
                row.state = state.value
            self._merge_references(row, recovery_refs)
            row.updated_at = self.clock()
            return _record(row)

    stage = phase

    @_complete_write
    async def retain_artifact(self, operation_id: str, resource: ResourceReference) -> None:
        async with self._write() as session:
            row = await self._row(session, operation_id)
            self._active(row)
            resources = _record(row).resources
            if not resource.path or resource.server_id is None or not any(
                (parent.server_id, parent.generation) == (resource.server_id, resource.generation)
                for parent in resources
            ):
                raise InvalidOperationTransition()
            if resource not in resources:
                row.resources_json = _resources((*resources, resource), self.limits.max_resources)
                row.updated_at = self.clock()

    @_complete_write
    async def resolve_reference(self, operation_id: str, kind: str, value: str) -> None:
        async with self._write() as session:
            row = await self._row(session, operation_id)
            self._merge_references(row, (RecoveryReference(kind, value, resolved=True),))
            row.updated_at = self.clock()

    def _merge_references(self, row: OperationJournalEntry, values: Sequence[RecoveryReference]) -> None:
        references = {(value["kind"], value["value"]): RecoveryReference(**value)
                      for value in json.loads(row.recovery_refs_json)}
        for value in values:
            _token(value.kind, maximum=40)
            _token(value.value)
            references[(value.kind, value.value)] = value
        if len(references) > self.limits.max_recovery_refs:
            raise ValueError("Too many retained recovery references")
        row.recovery_refs_json = _encode(tuple(references.values()))
        row.has_recovery_refs = any(not value.resolved for value in references.values())

    @_complete_write
    async def finish(
        self, operation_id: str, state: OperationState, *, writers_stopped: bool,
        failure_code: str | None = None, recovery_refs: Sequence[RecoveryReference] = (),
        changed: bool = False, cache_degraded: bool = False,
        blocked_reason: str | None = None,
    ) -> OperationRecord:
        if state not in TERMINAL_STATES:
            raise InvalidOperationTransition()
        if failure_code is not None:
            _token(failure_code)
        if blocked_reason is not None:
            _token(blocked_reason)
        async with self._write() as session:
            row = await self._row(session, operation_id)
            self._active(row)
            if writers_stopped and (not row.ownership_known or json.loads(row.processes_json)):
                raise InvalidOperationTransition()
            if not writers_stopped and state in {OperationState.SUCCEEDED, OperationState.CANCELLED, OperationState.SKIPPED}:
                raise InvalidOperationTransition()
            now = self.clock()
            row.state, row.updated_at, row.ended_at = state.value, now, now
            row.writers_stopped = writers_stopped
            row.data_changed = row.data_changed or changed
            row.failure_code = failure_code
            row.blocked_reason = blocked_reason if writers_stopped else "writers_unconfirmed"
            row.cache_degraded = row.cache_degraded or cache_degraded
            self._merge_references(row, recovery_refs)
            return _record(row)

    @_complete_write
    async def register_process(self, operation_id: str, identity: ProcessIdentity) -> OperationRecord:
        if min(identity.pid, identity.pgid, identity.root_ino) < 1 or min(identity.start_ticks, identity.root_dev) < 0:
            raise ValueError("Invalid process identity")
        _token(identity.boot_id)
        async with self._write() as session:
            row = await self._row(session, operation_id)
            self._active(row)
            identities = [ProcessIdentity(**value) for value in json.loads(row.processes_json)]
            if identity in identities:
                return _record(row)
            if len(identities) >= self.limits.max_processes:
                raise JournalCapacityError()
            if any(value.pid == identity.pid for value in identities):
                raise InvalidOperationTransition()
            row.processes_json = _encode([*identities, identity])
            row.writers_stopped = False
            row.updated_at = self.clock()
            return _record(row)

    @_complete_write
    async def process_stopped(self, operation_id: str, pid: int, start_ticks: int) -> bool:
        async with self._write() as session:
            row = await self._row(session, operation_id)
            identities = [ProcessIdentity(**value) for value in json.loads(row.processes_json)]
            retained = [value for value in identities if (value.pid, value.start_ticks) != (pid, start_ticks)]
            if len(retained) == len(identities):
                return False
            row.processes_json = _encode(retained)
            row.updated_at = self.clock()
            return True

    @_complete_write
    async def set_ownership_known(self, operation_id: str, known: bool) -> None:
        async with self._write() as session:
            row = await self._row(session, operation_id)
            self._active(row)
            row.ownership_known = known
            if not known:
                row.writers_stopped = False
            row.updated_at = self.clock()

    @_complete_write
    async def capture_running_intent(self, operation_id: str, running: bool) -> None:
        async with self._write() as session:
            row = await self._row(session, operation_id)
            self._active(row)
            row.running_intent = running
            row.updated_at = self.clock()

    @_complete_write
    async def mark_cache_degraded(self, operation_id: str) -> None:
        async with self._write() as session:
            row = await self._row(session, operation_id)
            self._active(row)
            row.cache_degraded = True
            row.updated_at = self.clock()

    @_complete_write
    async def recover_interrupted(
        self, operation_id: str, *, writers_stopped: bool, blocked_reason: str | None,
        cache_degraded: bool = False,
    ) -> OperationRecord:
        if blocked_reason is not None:
            _token(blocked_reason)
        async with self._write() as session:
            row = await self._row(session, operation_id)
            if OperationState(row.state) not in TERMINAL_STATES:
                row.state = OperationState.INTERRUPTED.value
                row.failure_code = "backend_interrupted"
                row.ended_at = self.clock()
            row.writers_stopped = writers_stopped
            if writers_stopped:
                row.processes_json = "[]"
                row.ownership_known = True
            row.blocked_reason = blocked_reason
            row.cache_degraded = cache_degraded
            row.updated_at = self.clock()
            return _record(row)

    @_complete_write
    async def resolve(
        self, operation_id: str, *, actor_id: int, writers_stopped: bool,
        resolve_references: bool = False,
    ) -> OperationRecord:
        if not writers_stopped:
            raise InvalidOperationTransition()
        async with self._write() as session:
            row = await self._row(session, operation_id)
            if OperationState(row.state) not in TERMINAL_STATES:
                raise InvalidOperationTransition()
            row.writers_stopped, row.ownership_known = True, True
            row.processes_json, row.blocked_reason = "[]", None
            if resolve_references:
                values = [RecoveryReference(value["kind"], value["value"], resolved=True)
                          for value in json.loads(row.recovery_refs_json)]
                row.recovery_refs_json, row.has_recovery_refs = _encode(values), False
            row.resolved_by, row.resolved_at = actor_id, self.clock()
            row.updated_at = self.clock()
            return _record(row)

    @_complete_read
    async def get(self, operation_id: str) -> OperationRecord | None:
        async with self.session_factory() as session:
            row = await session.get(OperationJournalEntry, operation_id)
            return _record(row) if row is not None else None

    @_complete_read
    async def list(
        self, *, limit: int = 100, offset: int = 0, origin: str | None = None,
        legacy_id: str | None = None,
    ) -> list[OperationRecord]:
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError("Operation history pagination is bounded")
        query = select(OperationJournalEntry)
        if origin is not None:
            query = query.where(OperationJournalEntry.origin == origin)
        if legacy_id is not None:
            query = query.where(OperationJournalEntry.legacy_id == legacy_id)
        query = query.order_by(OperationJournalEntry.created_at.desc(), OperationJournalEntry.operation_id).limit(limit).offset(offset)
        async with self.session_factory() as session:
            return [_record(row) for row in (await session.scalars(query)).all()]

    @_complete_read
    async def unsettled(self) -> builtins.list[OperationRecord]:
        query = select(OperationJournalEntry).where(
            OperationJournalEntry.state.not_in([state.value for state in TERMINAL_STATES])
            | OperationJournalEntry.blocked_reason.is_not(None)
            | OperationJournalEntry.writers_stopped.is_(False)
            | OperationJournalEntry.cache_degraded.is_(True)
            | OperationJournalEntry.has_recovery_refs.is_(True)
        ).order_by(OperationJournalEntry.created_at, OperationJournalEntry.operation_id)
        async with self.session_factory() as session:
            records = [_record(row) for row in (await session.scalars(query)).all()]
            return [record for record in records if (
                record.state not in TERMINAL_STATES or record.blocked_reason is not None
                or not record.writers_stopped or record.cache_degraded
                or any(reference.kind in {"configuration_stage", "archive_stage", "population_stage"} and not reference.resolved for reference in record.recovery_refs)
            )]

    async def _prune(self, session: AsyncSession, *, reserve: int = 0) -> int:
        eligible = (
            OperationJournalEntry.state.in_([state.value for state in TERMINAL_STATES]),
            OperationJournalEntry.writers_stopped.is_(True),
            OperationJournalEntry.has_recovery_refs.is_(False),
            OperationJournalEntry.blocked_reason.is_(None),
            OperationJournalEntry.cache_degraded.is_(False),
        )
        expired = delete(OperationJournalEntry).where(*eligible, OperationJournalEntry.ended_at < self.clock() - self.limits.terminal_max_age).returning(OperationJournalEntry.operation_id)
        removed = len((await session.scalars(expired)).all())
        count = await session.scalar(select(func.count()).select_from(OperationJournalEntry)) or 0
        excess = max(0, count + reserve - self.limits.max_records)
        if excess:
            oldest = select(OperationJournalEntry.operation_id).where(*eligible).order_by(OperationJournalEntry.ended_at, OperationJournalEntry.operation_id).limit(excess)
            removed += len((await session.scalars(delete(OperationJournalEntry).where(OperationJournalEntry.operation_id.in_(oldest)).returning(OperationJournalEntry.operation_id))).all())
        return removed

    @_complete_write
    async def prune(self) -> int:
        async with self._write() as session:
            return await self._prune(session)
