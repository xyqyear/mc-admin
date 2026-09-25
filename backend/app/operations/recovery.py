import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal, Protocol

from fastapi import HTTPException
from sqlalchemy import select

from app.servers.models import Server, ServerStatus

from ..errors import log_safe_error
from ..servers.references import resolve_server_ref
from ..utils import async_fs
from .journal import InvalidOperationTransition, OperationJournal
from .journal_types import (
    TERMINAL_STATES,
    OperationRecord,
    RecoveryBlock,
    RecoveryReport,
    ResourceReference,
)
from .processes import confirm_stopped

ResolveAction = Literal["acknowledge_partial", "configuration_reconciled"]
ProcessProbe = Callable[[OperationRecord], Awaitable[bool]]
ResourceValidator = Callable[[ResourceReference], Awaitable[bool]]
CacheInvalidator = Callable[[ResourceReference], Awaitable[None]]
ConfigurationVerifier = Callable[[OperationRecord], Awaitable[bool]]

REASONS = {
    "writers_unconfirmed": "中断操作的写入尚未确认结束，请检查操作历史并停止所属写入后重新验证",
    "target_generation_changed": "历史操作的服务器实例已变更，不能将恢复操作应用到同名新实例",
    "configuration_reconciliation_required": "配置操作已中断，请核对当前配置与模板来源一致后解除限制",
}


class RecoveryAdmission(Protocol):
    def block(self, server_id: str, reason: str) -> None: ...
    def unblock(self, server_id: str) -> None: ...
    def block_global(self, reason: str) -> None: ...
    def unblock_global(self) -> None: ...
    def block_archive(self, path: str, reason: str) -> None: ...
    def unblock_archive(self, path: str) -> None: ...


class RecoveryService:
    def __init__(
        self, journal: OperationJournal, *, probe: ProcessProbe = confirm_stopped,
        servers_root: Path | None = None,
        archive_root: Path | None = None,
        validate_resource: ResourceValidator | None = None,
        invalidate_cache: CacheInvalidator | None = None,
        configuration_consistent: ConfigurationVerifier | None = None,
    ) -> None:
        self.journal, self.probe, self.servers_root = journal, probe, servers_root
        self.archive_root = archive_root
        self.validate_resource = validate_resource or self._validate_resource
        self.invalidate_cache = invalidate_cache or self._invalidate_cache
        self.configuration_consistent = configuration_consistent or self._configuration_consistent
        self.degraded_resources: set[ResourceReference] = set()
        self._installed_blocks: set[str] = set()
        self._global_block = False
        self._archive_blocks: set[str] = set()
        self._lock = asyncio.Lock()

    async def _validate_resource(self, resource: ResourceReference) -> bool:
        if resource.server_id is None:
            return True
        if self.servers_root is None:
            return False
        async with self.journal.session_factory() as session:
            try:
                reference = await resolve_server_ref(
                    session, resource.server_id, servers_root=self.servers_root, require_exists=False,
                )
            except HTTPException:
                return False
            return reference.generation == resource.generation

    async def _invalidate_cache(self, resource: ResourceReference) -> None:
        if resource.server_id is None or self.servers_root is None:
            raise RuntimeError("Cannot resolve the owned map cache")
        async with self.journal.session_factory() as session:
            reference = await resolve_server_ref(
                session, resource.server_id, servers_root=self.servers_root, require_exists=False,
            )
            if reference.generation != resource.generation:
                raise InvalidOperationTransition()
        try:
            tiles = reference.data_path / ".mcmap" / "tiles"
            await async_fs.resolve_inside(reference.data_path, tiles)
            await async_fs.rmtree(tiles)
        except FileNotFoundError:
            pass

    async def _configuration_consistent(self, record: OperationRecord) -> bool:
        if self.servers_root is None:
            return False
        from ..configuration.preparation import (
            prepare_snapshot_configuration,
            validate_server_configuration,
        )
        from ..configuration.state import read_configuration_state

        for resource in record.resources:
            if resource.server_id is None:
                continue
            async with self.journal.session_factory() as session:
                row = await session.scalar(select(Server).where(
                    Server.id == resource.generation, Server.server_id == resource.server_id,
                    Server.status == ServerStatus.ACTIVE,
                ))
                if row is None:
                    return False
                current = await read_configuration_state(session, resource.server_id, self.servers_root)
                content = current.yaml_content
                await asyncio.to_thread(validate_server_configuration, resource.server_id, content)
                evidence = {reference.kind: reference.value for reference in record.recovery_refs}
                if evidence.get("configuration_baseline") == current.version:
                    continue
                if record.configuration_version is not None and hashlib.sha256(content.encode()).hexdigest() != record.configuration_version:
                    return False
                if source := evidence.get("configuration_source"):
                    if source != current.source_version:
                        return False
                elif row.template_id is not None:
                    expected = prepare_snapshot_configuration(row, json.loads(row.variable_values_json or "{}"))
                    if content != expected.yaml_content:
                        return False
        return True

    async def _clean_configuration_stages(self, record: OperationRecord) -> None:
        from ..configuration.files import stage_path

        if self.servers_root is None:
            return
        for reference in record.recovery_refs:
            if reference.kind != "configuration_stage" or reference.resolved:
                continue
            if not re.fullmatch(r"[a-f0-9]{32}", reference.value):
                continue
            artifacts = [resource for resource in record.resources if resource.kind == "configuration_stage" and Path(resource.path).name == stage_path(Path(), reference.value).name]
            resources = artifacts or [resource for resource in record.resources if resource.kind != "configuration_stage"]
            for resource in resources:
                if resource.server_id is None:
                    continue
                async with self.journal.session_factory() as session:
                    server = await resolve_server_ref(session, resource.server_id, servers_root=self.servers_root)
                    if server.generation != resource.generation:
                        continue
                    target = server.project_path / resource.path if artifacts else stage_path(server.project_path, reference.value)
                    parent = await async_fs.resolve_inside(server.project_path, target.parent)
                    if parent != target.parent:
                        raise InvalidOperationTransition()
                    await asyncio.to_thread(target.unlink, missing_ok=True)
            await self.journal.resolve_reference(record.operation_id, reference.kind, reference.value)

    async def _stopped(self, record: OperationRecord) -> bool:
        try:
            return await self.probe(record)
        except Exception as error:  # noqa: BLE001 - failed ownership verification must keep writes blocked
            log_safe_error(error, "Operation ownership verification failed")
            return False

    async def _clean_file_stages(self, record: OperationRecord) -> None:
        for reference in record.recovery_refs:
            if reference.resolved or reference.kind not in {"archive_stage", "population_stage"}:
                continue
            if not re.fullmatch(r"[a-f0-9]{32}", reference.value):
                raise InvalidOperationTransition()
            archive = reference.kind == "archive_stage"
            name = f".mc-admin-{'archive' if archive else 'populate'}-{reference.value}.tmp"
            artifacts = [resource for resource in record.resources if resource.kind == ("archive" if archive else "files") and Path(resource.path).name == name]
            if len(artifacts) != 1:
                raise InvalidOperationTransition()
            resource = artifacts[0]
            if archive:
                if self.archive_root is None or resource.server_id is not None:
                    raise InvalidOperationTransition()
                root = await async_fs.resolve(self.archive_root)
            else:
                if self.servers_root is None or resource.server_id is None:
                    raise InvalidOperationTransition()
                async with self.journal.session_factory() as session:
                    server = await resolve_server_ref(session, resource.server_id, servers_root=self.servers_root)
                    if server.generation != resource.generation:
                        raise InvalidOperationTransition()
                    root = server.project_path
            target = root / resource.path
            if await async_fs.resolve_inside(root, target.parent) != target.parent:
                raise InvalidOperationTransition()
            try:
                if archive:
                    await asyncio.to_thread(target.unlink, missing_ok=True)
                else:
                    await async_fs.resolve_inside(root, target)
                    await async_fs.rmtree(target)
            except FileNotFoundError:
                pass
            await self.journal.resolve_reference(record.operation_id, reference.kind, reference.value)

    async def _target_valid(self, resource: ResourceReference) -> bool:
        try:
            return await self.validate_resource(resource)
        except Exception as error:  # noqa: BLE001 - target ambiguity must never enable recovery writes
            log_safe_error(error, "Operation target verification failed")
            return False

    @staticmethod
    def _configuration(record: OperationRecord) -> bool:
        return record.kind in {"server_rebuild", "configuration_apply"} or any(
            resource.kind in {"configuration", "server_configuration"} for resource in record.resources
        )

    @classmethod
    def configuration_changed(cls, record: OperationRecord) -> bool:
        return record.data_changed and cls._configuration(record)

    async def _consistent(self, record: OperationRecord) -> bool:
        try:
            return await self.configuration_consistent(record)
        except Exception as error:  # noqa: BLE001 - inconclusive configuration evidence is not a successful reconciliation
            log_safe_error(error, "Operation configuration verification failed")
            return False

    @staticmethod
    def _cache_affected(record: OperationRecord, resource: ResourceReference) -> bool:
        return resource.server_id is not None and (
            record.cache_degraded or resource.kind == "cache"
            or (record.data_changed and resource.kind in {"world", "files", "data", "server_data"})
        )

    async def _reconcile_record(self, record: OperationRecord) -> OperationRecord:
        stopped = record.writers_stopped or await self._stopped(record)
        valid = all([await self._target_valid(resource) for resource in record.resources])
        if stopped and valid:
            try:
                await self._clean_configuration_stages(record)
                await self._clean_file_stages(record)
            except Exception as error:  # noqa: BLE001 - unresolved stages retain their cleanup ownership
                log_safe_error(error, "Configuration staging cleanup failed")
        reason = None
        if not stopped:
            reason = "writers_unconfirmed"
        elif not valid:
            reason = "target_generation_changed"
        elif self.configuration_changed(record) and not await self._consistent(record):
            reason = "configuration_reconciliation_required"
        degraded = False
        for resource in record.resources:
            if self._cache_affected(record, resource):
                if not stopped or not await self._target_valid(resource):
                    degraded = True
                    self.degraded_resources.add(resource)
                    continue
                try:
                    await self.invalidate_cache(resource)
                except Exception as error:  # noqa: BLE001 - unavailable cache must not freeze unrelated server management
                    log_safe_error(error, "Operation cache recovery degraded")
                    degraded = True
                    self.degraded_resources.add(resource)
        return await self.journal.recover_interrupted(
            record.operation_id, writers_stopped=stopped, blocked_reason=reason,
            cache_degraded=degraded,
        )

    async def reconcile_terminal(self, operation_id: str) -> OperationRecord:
        async with self._lock:
            record = await self.journal.get(operation_id)
            if record is None:
                raise KeyError(operation_id)
            if record.state not in TERMINAL_STATES:
                raise InvalidOperationTransition()
            updated = await self._reconcile_record(record)
            await self.report()
            return updated

    async def recover(self) -> RecoveryReport:
        interrupted = []
        async with self._lock:
            self.degraded_resources.clear()
            for record in await self.journal.unsettled():
                updated = await self._reconcile_record(record)
                if record.state not in TERMINAL_STATES:
                    interrupted.append(updated.operation_id)
            await self.journal.prune()
            report = await self.report()
            return RecoveryReport(tuple(interrupted), report.blocks, report.degraded_resources)

    async def report(self) -> RecoveryReport:
        blocks: list[RecoveryBlock] = []
        degraded: set[ResourceReference] = set()
        records = await self.journal.unsettled()
        active = {
            (resource.server_id, resource.generation)
            for record in records if record.state not in TERMINAL_STATES
            for resource in record.resources
        }
        for record in records:
            for resource in record.resources:
                if record.blocked_reason is not None:
                    blocks.append(RecoveryBlock(record.operation_id, resource, record.blocked_reason))
                if record.cache_degraded and resource.server_id is not None:
                    degraded.add(resource)
        degraded.update(resource for resource in self.degraded_resources if (resource.server_id, resource.generation) in active)
        self.degraded_resources = degraded
        return RecoveryReport(blocks=tuple(blocks), degraded_resources=tuple(sorted(degraded, key=repr)))

    async def apply_blocks(self, admission: RecoveryAdmission) -> RecoveryReport:
        report = await self.report()
        blocked: dict[str, str] = {}
        global_reason = None
        archives: dict[str, str] = {}
        for block in report.blocks:
            resource = block.resource
            if resource.kind == "archive":
                archives[resource.path] = REASONS.get(block.reason, "压缩包有待处理的中断操作")
            elif resource.server_id is None and resource.kind != "cache":
                global_reason = REASONS.get(block.reason, "全局资源有待处理的中断操作")
            if resource.server_id is not None and resource.kind != "cache" and await self._target_valid(resource):
                blocked.setdefault(resource.server_id, REASONS.get(block.reason, "服务器有待处理的中断操作"))
        if global_reason is not None:
            admission.block_global(global_reason)
        elif self._global_block:
            admission.unblock_global()
        self._global_block = global_reason is not None
        for server_id in self._installed_blocks - blocked.keys():
            admission.unblock(server_id)
        for server_id, reason in blocked.items():
            admission.block(server_id, reason)
        self._installed_blocks = set(blocked)
        for path in self._archive_blocks - archives.keys():
            admission.unblock_archive(path)
        for path, reason in archives.items():
            admission.block_archive(path, reason)
        self._archive_blocks = set(archives)
        return report

    async def resolve(
        self, operation_id: str, *, actor_id: int, action: ResolveAction,
        resolve_references: bool = False,
    ) -> OperationRecord:
        async with self._lock:
            record = await self.journal.get(operation_id)
            if record is None:
                raise HTTPException(status_code=404, detail="操作记录不存在")
            if record.state not in TERMINAL_STATES:
                raise HTTPException(status_code=409, detail="操作仍未结束，不能解除恢复限制")
            if not await self._stopped(record):
                raise HTTPException(status_code=409, detail=REASONS["writers_unconfirmed"])
            if not all([await self._target_valid(resource) for resource in record.resources]):
                raise HTTPException(status_code=409, detail=REASONS["target_generation_changed"])
            if self.configuration_changed(record) and (action != "configuration_reconciled" or not await self._consistent(record)):
                raise HTTPException(status_code=409, detail=REASONS["configuration_reconciliation_required"])
            return await self.journal.resolve(
                operation_id, actor_id=actor_id, writers_stopped=True,
                resolve_references=resolve_references,
            )
