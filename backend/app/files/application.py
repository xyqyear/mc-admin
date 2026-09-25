"""Owned server file writes without locking unrelated files or safe reads."""

from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import aclosing
from pathlib import Path
from typing import TypeVar

from fastapi import UploadFile

from ..background_tasks import TaskProgress
from ..minecraft import MCInstance
from ..operations.context import record_phase
from ..operations.coordinator import (
    ConflictPolicy,
    ResourceClaim,
    get_operation_coordinator,
)
from ..operations.execution import operation_scope, settle_before_release
from ..operations.finalization import finalize
from . import base, multi_file
from .paths import resolve_file_path, validate_file_name
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
