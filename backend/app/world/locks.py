"""Per-server async operation lock for backup/restore mutual exclusion."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import AsyncIterator, Optional

GLOBAL_LOCK_KEY = "__global__"


class ServerOperationKind(str, Enum):
    BACKUP = "backup"
    RESTORE = "restore"


@dataclass
class LockHolder:
    kind: ServerOperationKind
    started_at: datetime
    user_id: Optional[int]
    description: str
    restoration_id: Optional[str] = None


class ServerOperationLock:
    """Per-server async mutex.

    Acquired via the ``acquire`` async context manager, which guarantees
    release via ``try/finally`` even on exception. Map render queues
    intentionally do NOT use this lock — only mutating world operations
    (backup, restore) take it.
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
    ) -> AsyncIterator[None]:
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
    ) -> AsyncIterator[bool]:
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

    def get_holder(self, server_id: str) -> Optional[LockHolder]:
        return self._holders.get(server_id)


server_operation_lock = ServerOperationLock()
