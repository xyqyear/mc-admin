import asyncio
from contextlib import aclosing
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.snapshots import ResticClient, SnapshotService
from app.snapshots.repository_use import RepositoryUse


def test_accepted_work_and_preview_keep_sources_until_the_last_owner_leaves():
    repository = RepositoryUse()
    with repository.retain(["source"]):
        with repository.retain(["source", "safety"]):
            assert repository.active_snapshots == {"source", "safety"}
            with pytest.raises(HTTPException) as caught, repository.maintain():
                pass
            assert caught.value.status_code == 423
        assert repository.active_snapshots == {"source"}
    with repository.maintain():
        assert not repository.active_snapshots


async def test_cancelled_reader_releases_ownership_after_its_cleanup():
    repository = RepositoryUse()
    started, finish_cleanup, cleaning = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )

    async def run():
        with repository.retain(["source"]):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await finish_cleanup.wait()

    task = asyncio.create_task(run())
    await started.wait()
    task.cancel()
    await cleaning.wait()
    with pytest.raises(HTTPException), repository.maintain():
        pass
    finish_cleanup.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    with repository.maintain():
        assert not repository.active_snapshots


async def test_maintenance_blocks_admission_and_releases_after_failure():
    repository = RepositoryUse()
    with pytest.raises(RuntimeError), repository.maintain():
        with pytest.raises(HTTPException), repository.retain(["source"]):
            pass
        raise RuntimeError("repository unavailable")
    with repository.retain(["source"]):
        assert repository.active_snapshots == {"source"}


async def test_service_refuses_destructive_repository_calls_while_a_source_is_retained():
    client = Mock(spec=ResticClient)
    client.forget_id = AsyncMock(return_value="deleted")
    client.forget = AsyncMock(return_value="pruned")
    client.unlock = AsyncMock(return_value="unlocked")
    service = SnapshotService(client, Mock())
    with service.repository_use.retain(["source"]):
        for call in (
            service.forget_id("source"),
            service.forget(keep_last=1),
            service.unlock(),
        ):
            with pytest.raises(HTTPException) as caught:
                await call
            assert caught.value.status_code == 423
    client.forget_id.assert_not_called()
    client.forget.assert_not_called()
    client.unlock.assert_not_called()
    assert await service.forget_id("source") == "deleted"


async def test_restore_stream_keeps_repository_owned_through_generator_cleanup(
    monkeypatch, tmp_path
):
    service = SnapshotService(Mock(spec=ResticClient), Mock())
    monkeypatch.setattr(service, "build_plan", AsyncMock())

    async def events(*args, **kwargs):
        yield "progress"
        await asyncio.Event().wait()

    monkeypatch.setattr(service, "_run_plan", events)
    async with aclosing(service.restore("source", [tmp_path])) as stream:
        assert await anext(stream) == "progress"
        with pytest.raises(HTTPException):
            await service.forget_id("source")
    with service.repository_use.maintain():
        assert not service.repository_use.active_snapshots
