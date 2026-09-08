"""Per-server maintenance ownership shared by snapshots, world writes and startup."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

GLOBAL_LOCK_KEY = "__global__"


class ServerOperationKind(str, Enum):
    BACKUP = "backup"
    RESTORE = "restore"
    PRUNE = "prune"
    START = "start"


@dataclass
class LockHolder:
    kind: ServerOperationKind
    started_at: datetime
    user_id: int | None
    description: str
    restoration_id: str | None = None


class ServerOperationLock:
    """Per-server async mutex.

    Acquired via the ``acquire`` async context manager, which guarantees
    release via ``try/finally`` even on exception. Map render queues
    intentionally do NOT use this lock. Backup, restore, prune and startup
    share ownership so stopped-world writes cannot overlap server startup.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._holders: dict[str, LockHolder] = {}

    def _lock_for(self, server_id: str) -> asyncio.Lock:
        lock = self._locks.get(server_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[server_id] = lock
        return lock

    @asynccontextmanager
    async def acquire(
        self, server_id: str, holder: LockHolder
    ) -> AsyncGenerator[None]:
        lock = self._lock_for(server_id)
        await lock.acquire()
        try:
            self._holders[server_id] = holder
            yield
        finally:
            self._holders.pop(server_id, None)
            lock.release()

    @asynccontextmanager
    async def try_acquire(
        self, server_id: str, holder: LockHolder
    ) -> AsyncGenerator[bool]:
        lock = self._lock_for(server_id)
        if lock.locked():
            yield False
        else:
            await lock.acquire()
            try:
                self._holders[server_id] = holder
                yield True
            finally:
                self._holders.pop(server_id, None)
                lock.release()

    def is_locked(self, server_id: str) -> bool:
        lock = self._locks.get(server_id)
        return lock is not None and lock.locked()

    @asynccontextmanager
    async def try_acquire_servers(
        self, server_ids: list[str], holder: LockHolder
    ) -> AsyncGenerator[bool]:
        async with AsyncExitStack() as stack:
            for server_id in sorted(set(server_ids)):
                if not await stack.enter_async_context(self.try_acquire(server_id, holder)):
                    await stack.aclose()
                    yield False
                    return
            yield True

    def get_holder(self, server_id: str) -> LockHolder | None:
        return self._holders.get(server_id)

    def get_holders(self) -> dict[str, LockHolder]:
        return dict(self._holders)


server_operation_lock = ServerOperationLock()
