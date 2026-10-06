"""Owned server file writes without locking unrelated files or safe reads."""

from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import aclosing
from pathlib import Path
from typing import TypeVar

from aiofiles import os as aioos
from fastapi import HTTPException, UploadFile

from ..background_tasks import TaskProgress, TaskType, get_task_manager
from ..background_tasks.api_models import TaskAccepted
from ..errors import PublicOperationError, log_safe_error
from ..minecraft import MCInstance
from ..operations.context import current_execution, record_phase
from ..operations.coordinator import (
    ConflictPolicy,
    ResourceClaim,
    get_operation_coordinator,
)
from ..operations.execution import operation_scope, settle_before_release
from ..operations.finalization import finalize
from . import base, multi_file
from .paths import normalize_selected_paths, resolve_file_path, validate_file_name
from .resources import path_claims, require_same_claims
from .types import CreateFileRequest, RenameFileRequest

T = TypeVar("T")


class FileApplication:
    def __init__(self, instance: MCInstance, server_id: str, actor_id: int | None = None) -> None:
        self.instance = instance
        self.server_id = server_id
        self.actor_id = actor_id

    async def claims(self, paths: Sequence[Path]) -> tuple[ResourceClaim, ...]:
        return await path_claims(self.instance.get_project_path(), paths, server_id=self.server_id)

    async def _write(self, kind: str, paths: Sequence[Path], action: Callable[[], Awaitable[T]], *, finish_on_cancel: bool = True) -> T:
        claims = await self.claims(paths)
        async with (
            operation_scope(kind, [self.server_id], actor_id=self.actor_id, claims=claims),
            get_operation_coordinator().acquire(claims, policy=ConflictPolicy.REJECT),
            settle_before_release(),
        ):
            require_same_claims(claims, await self.claims(paths))
            await record_phase("writing_files", changed=True)
            return await finalize(action()) if finish_on_cancel else await action()

    async def update(self, path: str, content: str) -> None:
        data = self.instance.get_data_path()
        target = await resolve_file_path(data, path)
        await self._write("file_write", [target], lambda: base.update_file_content(data, path, content))

    async def create(self, request: CreateFileRequest) -> str:
        validate_file_name(request.name)
        data = self.instance.get_data_path()
        target = await resolve_file_path(data, str(Path(request.path) / request.name))
        return await self._write("file_create", [target], lambda: base.create_file_or_directory(data, request))

    async def delete(self, path: str) -> str:
        data = self.instance.get_data_path()
        target = await resolve_file_path(data, path)
        return await self._write("file_delete", [target], lambda: base.delete_file_or_directory(data, path))

    async def submit_delete(self, path: str) -> TaskAccepted:
        data = self.instance.get_data_path()
        target = await resolve_file_path(data, path)
        await base.validate_delete_target(data, path)
        claims = await self.claims([target])
        await get_operation_coordinator().check_available(claims)

        async def run() -> AsyncGenerator[TaskProgress]:
            yield TaskProgress(message=f"正在删除 {path}")
            message = await self.delete(path)
            yield TaskProgress(progress=100, message=message, result={"message": message, "path": path})

        submitted = await get_task_manager().submit_durable(
            TaskType.FILE_DELETE, f"删除 {self.server_id}/{path}", run(),
            server_id=self.server_id, actor_id=self.actor_id, claims=claims, cancellable=False,
            exclusive_key=f"file-delete:{target}",
        )
        return TaskAccepted(task_id=submitted.task_id)

    async def submit_delete_batch(self, paths: Sequence[str]) -> TaskAccepted:
        data = self.instance.get_data_path()
        for path in paths:
            await base.validate_delete_target(data, path)
        roots = await normalize_selected_paths(data, paths)
        targets = [await resolve_file_path(data, path) for path in roots]
        claims = await self.claims(targets)
        await get_operation_coordinator().check_available(claims)
        results = [{"path": path, "status": "pending", "message": "尚未执行"} for path in roots]

        def outcome() -> dict:
            return {
                "paths": list(roots), "results": [dict(result) for result in results],
                **{status: sum(result["status"] == status for result in results) for status in ("deleted", "failed", "pending")},
            }

        async def persist() -> None:
            execution = current_execution()
            if execution is not None:
                await execution.journal.save_task_result(execution.operation_id, outcome())

        async def retain_initial(operation_id: str) -> None:
            journal = get_task_manager().journal
            if journal is None:
                raise RuntimeError("批量删除需要持久化操作日志")
            await journal.save_task_result(operation_id, outcome())

        async def remove(result: dict[str, str]) -> None:
            try:
                target = await base.validate_delete_target(data, result["path"])
                if await aioos.path.islink(target):
                    await aioos.unlink(target)
                else:
                    await base.delete_file_or_directory(data, result["path"])
                result.update(status="deleted", message="删除成功")
            except (OSError, HTTPException) as error:
                log_safe_error(error, "Batch file deletion failed")
                result.update(status="failed", message="删除失败，请刷新文件列表后重试")
            await persist()

        async def run() -> AsyncGenerator[TaskProgress]:
            yield TaskProgress(message="正在准备批量删除", result=outcome())
            async with get_operation_coordinator().acquire(claims, policy=ConflictPolicy.REJECT), settle_before_release():
                require_same_claims(claims, await self.claims(targets))
                for path in roots:
                    await base.validate_delete_target(data, path)
                await record_phase("deleting_files", changed=True)
                for index, result in enumerate(results):
                    await finalize(remove(result))
                    yield TaskProgress(progress=(index + 1) * 100 / len(results), message=f"已处理 {index + 1}/{len(results)} 项", result=outcome())
            if any(result["status"] == "failed" for result in results):
                raise PublicOperationError("部分文件删除失败，请查看逐项结果")
            yield TaskProgress(progress=100, message="批量删除完成", result=outcome())

        submitted = await get_task_manager().submit_durable(
            TaskType.FILE_DELETE, f"批量删除 {self.server_id} 的 {len(roots)} 项", run(),
            server_id=self.server_id, actor_id=self.actor_id, claims=claims, cancellable=True,
            on_accepted=retain_initial,
        )
        return TaskAccepted(task_id=submitted.task_id)

    async def rename(self, request: RenameFileRequest) -> str:
        validate_file_name(request.new_name)
        data = self.instance.get_data_path()
        old = await resolve_file_path(data, request.old_path)
        target = await resolve_file_path(data, str((old.parent / request.new_name).relative_to(data)))
        return await self._write("file_rename", [old, target], lambda: base.rename_file_or_directory(data, request))

    async def upload(self, session_id: str, path: str, files: list[UploadFile]):
        multi_file.require_upload_session(session_id)
        data = self.instance.get_data_path()
        directory = await resolve_file_path(data, path)
        targets = [await resolve_file_path(directory, file.filename) for file in files if file.filename]
        return await self._write("file_upload", targets, lambda: multi_file.upload_multiple_files(data, session_id, path, files), finish_on_cancel=False)

    async def task(
        self, paths: Sequence[Path], events: AsyncGenerator[TaskProgress], *,
        claims: Sequence[ResourceClaim],
    ) -> AsyncGenerator[TaskProgress]:
        async with aclosing(events), get_operation_coordinator().acquire(claims, policy=ConflictPolicy.REJECT), settle_before_release():
            require_same_claims(claims, await self.claims(paths))
            await record_phase("writing_files", changed=True)
            async with aclosing(events):
                async for event in events:
                    yield event
