"""Admission and draining for server deletion, independent of maintenance mutexes."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import PurePosixPath

from fastapi import HTTPException

from .runtime_resources import current_runtime


class ServerWriteAdmission:
    def __init__(self) -> None:
        self._frozen: set[str] = set()
        self._freeze_owners: dict[str, object] = {}
        self._writers: dict[str, int] = {}
        self._global_writers = 0
        self._accepting = True
        self._blocked: dict[str, str] = {}
        self._global_block: str | None = None
        self._archive_blocks: dict[str, str] = {}

    def block_archive(self, path: str, reason: str) -> None:
        self._archive_blocks[path] = reason

    def unblock_archive(self, path: str) -> None:
        self._archive_blocks.pop(path, None)

    def check_archive(self, paths: Sequence[str]) -> None:
        if not self._accepting:
            raise HTTPException(status_code=503, detail="应用正在停止接收操作，请稍后重试")
        for path in paths:
            for blocked, reason in self._archive_blocks.items():
                if PurePosixPath(path).is_relative_to(PurePosixPath(blocked)) or PurePosixPath(blocked).is_relative_to(PurePosixPath(path)):
                    raise HTTPException(status_code=423, detail=reason)

    def block_global(self, reason: str) -> None:
        self._global_block = reason

    def unblock_global(self) -> None:
        self._global_block = None

    def close(self) -> None:
        self._accepting = False

    def open(self) -> None:
        self._accepting = True

    def block(self, server_id: str, reason: str) -> None:
        self._blocked[server_id] = reason

    def unblock(self, server_id: str) -> None:
        self._blocked.pop(server_id, None)

    def recovery_reason(self, server_id: str) -> str | None:
        return self._global_block or self._blocked.get(server_id)

    def is_frozen(self, server_id: str) -> bool:
        return server_id in self._frozen

    def check(self, server_id: str) -> None:
        if not self._accepting:
            raise HTTPException(status_code=503, detail="应用正在停止接收操作，请稍后重试")
        reason = self.recovery_reason(server_id)
        if reason:
            raise HTTPException(status_code=423, detail=reason)
        if self.is_frozen(server_id):
            raise HTTPException(status_code=423, detail="服务器正在删除，请等待操作完成")

    @contextmanager
    def write(self, server_ids: Sequence[str]) -> Iterator[None]:
        ids = set(server_ids)
        for server_id in ids:
            self.check(server_id)
        for server_id in ids:
            self._writers[server_id] = self._writers.get(server_id, 0) + 1
        try:
            yield
        finally:
            for server_id in ids:
                remaining = self._writers[server_id] - 1
                if remaining:
                    self._writers[server_id] = remaining
                else:
                    del self._writers[server_id]

    @contextmanager
    def freeze(self, server_id: str) -> Iterator[object]:
        self.check(server_id)
        permit = object()
        self._frozen.add(server_id)
        self._freeze_owners[server_id] = permit
        try:
            yield permit
        finally:
            self._frozen.remove(server_id)
            del self._freeze_owners[server_id]

    def validate_deletion(self, server_id: str, permit: object) -> None:
        if self._freeze_owners.get(server_id) is not permit:
            raise RuntimeError("删除操作不拥有该服务器的准入冻结")
        self.require_drained(server_id)

    @contextmanager
    def write_global(self) -> Iterator[None]:
        self.check("")
        if self._blocked:
            raise HTTPException(status_code=423, detail="有服务器需要处理中断操作，请先检查操作历史")
        if self._frozen:
            raise HTTPException(status_code=423, detail="服务器正在删除，请等待操作完成")
        self._global_writers += 1
        try:
            yield
        finally:
            self._global_writers -= 1

    def require_drained(self, server_id: str) -> None:
        if self._writers.get(server_id, 0) or self._global_writers:
            raise HTTPException(
                status_code=423, detail="服务器仍有文件或维护操作未结束，请稍后重试删除"
            )


def get_server_write_admission() -> ServerWriteAdmission:
    return current_runtime().resource('server_write_admission')
