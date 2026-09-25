import asyncio
from contextlib import aclosing
from datetime import UTC, datetime
from types import AsyncGeneratorType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.auth.models import UserRole
from app.auth.schemas import UserPublic
from app.routers.servers import world_restore
from app.world.models import RestorationType
from app.world.restore import RestoreEvent
from app.world.schemas import RestorationSelection


@pytest.mark.parametrize("event_type", ["complete", "error"])
async def test_restore_terminal_event_waits_for_owned_finalization(monkeypatch, event_type):
    cleaning, release = asyncio.Event(), asyncio.Event()

    async def restore(**kwargs):
        yield RestoreEvent(event_type="start")
        try:
            yield RestoreEvent(event_type=event_type)
        finally:
            cleaning.set()
            await release.wait()

    monkeypatch.setattr(world_restore, "_ensure_server_exists", AsyncMock())
    monkeypatch.setattr(world_restore, "_server_is_running", AsyncMock(return_value=False))
    monkeypatch.setattr(world_restore, "_get_orchestrator", lambda: SimpleNamespace(begin_restore=restore))
    scheduled = Mock()
    monkeypatch.setattr(world_restore, "schedule_self_check_event", scheduled)
    response = await world_restore.begin_restore(
        "owned", world_restore.RestoreRequest(source_snapshot_id="source", selection=RestorationSelection(type=RestorationType.WORLD)),
        UserPublic(id=1, username="owner", role=UserRole.OWNER, created_at=datetime.now(UTC)),
    )
    assert isinstance(response.body_iterator, AsyncGeneratorType)
    async with aclosing(response.body_iterator) as events:
        first = await anext(events)
        assert isinstance(first, bytes) and b'"start"' in first
        terminal = asyncio.create_task(anext(events))
        try:
            await asyncio.wait_for(cleaning.wait(), 1)
            assert not terminal.done()
            assert not scheduled.called
        finally:
            release.set()
        assert event_type.encode() in await asyncio.wait_for(terminal, 1)
    assert scheduled.call_count == (1 if event_type == "complete" else 0)
