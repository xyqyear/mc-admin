"""Tests for ServerOperationLock — acquire/release semantics, holder metadata."""

import asyncio
from datetime import datetime, timezone

import pytest

from app.world.locks import (
    LockHolder,
    ServerOperationKind,
    ServerOperationLock,
)


def _holder(kind: ServerOperationKind = ServerOperationKind.BACKUP) -> LockHolder:
    return LockHolder(
        kind=kind,
        started_at=datetime.now(timezone.utc),
        user_id=None,
        description="test",
    )


@pytest.mark.asyncio
async def test_acquire_releases_on_normal_exit():
    lock = ServerOperationLock()
    async with lock.acquire("srv1", _holder()):
        assert lock.is_locked("srv1")
        assert lock.get_holder("srv1") is not None
    assert not lock.is_locked("srv1")
    assert lock.get_holder("srv1") is None


@pytest.mark.asyncio
async def test_acquire_releases_on_exception():
    lock = ServerOperationLock()
    with pytest.raises(RuntimeError):
        async with lock.acquire("srv1", _holder()):
            assert lock.is_locked("srv1")
            raise RuntimeError("boom")
    assert not lock.is_locked("srv1")
    assert lock.get_holder("srv1") is None
    # And re-acquire succeeds
    async with lock.acquire("srv1", _holder()):
        assert lock.is_locked("srv1")


@pytest.mark.asyncio
async def test_locks_are_per_server():
    lock = ServerOperationLock()
    async with lock.acquire("srv1", _holder()):
        assert lock.is_locked("srv1")
        assert not lock.is_locked("srv2")
        async with lock.acquire("srv2", _holder()):
            assert lock.is_locked("srv2")


@pytest.mark.asyncio
async def test_concurrent_acquires_serialize():
    lock = ServerOperationLock()
    order: list[str] = []

    async def worker(name: str, hold_seconds: float):
        async with lock.acquire("srv1", _holder()):
            order.append(f"{name}-start")
            await asyncio.sleep(hold_seconds)
            order.append(f"{name}-end")

    await asyncio.gather(worker("a", 0.05), worker("b", 0.05))

    # Whichever started first must end before the other starts.
    assert order[0].endswith("-start")
    assert order[1].endswith("-end")
    assert order[2].endswith("-start")
    assert order[3].endswith("-end")
    assert order[0].split("-")[0] == order[1].split("-")[0]
    assert order[2].split("-")[0] == order[3].split("-")[0]


@pytest.mark.asyncio
async def test_holder_reflects_metadata():
    lock = ServerOperationLock()
    holder = LockHolder(
        kind=ServerOperationKind.RESTORE,
        started_at=datetime.now(timezone.utc),
        user_id=42,
        description="restore from snap",
        restoration_id="rest-abc",
    )
    async with lock.acquire("srv1", holder):
        observed = lock.get_holder("srv1")
        assert observed is not None
        assert observed.kind == ServerOperationKind.RESTORE
        assert observed.user_id == 42
        assert observed.restoration_id == "rest-abc"


@pytest.mark.asyncio
async def test_is_locked_unknown_server_is_false():
    lock = ServerOperationLock()
    assert lock.is_locked("srv-nope") is False
    assert lock.get_holder("srv-nope") is None
