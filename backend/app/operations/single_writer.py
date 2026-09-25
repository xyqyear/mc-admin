import asyncio
import fcntl
import os
from pathlib import Path
from types import TracebackType
from typing import Self

from sqlalchemy.engine import make_url

from .finalization import finalize


class SingleWriterGuard:
    """Hold kernel leases for both the database and the managed server root."""

    def __init__(self, database_url: str, server_path: Path) -> None:
        url = make_url(database_url)
        if url.get_backend_name() != "sqlite":
            raise RuntimeError("当前操作协调仅支持单写入进程的 SQLite 部署")
        self.server_path = server_path
        self.database_path = Path(url.database) if url.database and url.database != ":memory:" else None
        self._descriptors: list[int] = []

    def _acquire(self) -> None:
        if self._descriptors:
            raise RuntimeError("写入进程租约不能重复获取")
        self.server_path.mkdir(parents=True, exist_ok=True)
        paths = {self.server_path.resolve() / ".mc-admin-writer.lock"}
        if self.database_path is not None:
            database_path = self.database_path.resolve()
            database_path.parent.mkdir(parents=True, exist_ok=True)
            paths.add(database_path.with_name(database_path.name + ".writer.lock"))
        try:
            for path in sorted(paths):
                descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    os.close(descriptor)
                    raise RuntimeError("此数据库或服务器目录已有后端写入进程；请使用单 worker、单副本部署") from error
                except BaseException:
                    os.close(descriptor)
                    raise
                self._descriptors.append(descriptor)
        except BaseException:
            self._release()
            raise

    def _release(self) -> None:
        for descriptor in reversed(self._descriptors):
            os.close(descriptor)
        self._descriptors.clear()

    async def __aenter__(self) -> Self:
        try:
            await finalize(asyncio.to_thread(self._acquire))
        except BaseException:
            await finalize(asyncio.to_thread(self._release))
            raise
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None,
        exc: BaseException | None, traceback: TracebackType | None,
    ) -> None:
        await finalize(asyncio.to_thread(self._release))
