"""Lifespan crash recovery: any restoration row with status=running on
backend startup should flip to interrupted with an error message and a
finished_at timestamp."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import (
    Base,
    Restoration,
    RestorationStatus,
    RestorationType,
)
from app.routers.servers.world_restore import mark_running_restorations_interrupted


@pytest_asyncio.fixture
async def session_factory():
    with tempfile.TemporaryDirectory(prefix="mc-restore-crash-db-") as tmp:
        db_path = Path(tmp) / "test.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            yield maker
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_running_rows_become_interrupted(session_factory):
    started = datetime.now(timezone.utc) - timedelta(minutes=10)
    async with session_factory() as session:
        session.add(
            Restoration(
                id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                server_id="srv1",
                type=RestorationType.WORLD,
                source_snapshot_id="abc",
                safety_snapshot_id=None,
                selection_json='{"type":"world"}',
                is_rollback=False,
                started_at=started,
                status=RestorationStatus.RUNNING,
            )
        )
        session.add(
            Restoration(
                id="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                server_id="srv1",
                type=RestorationType.WORLD,
                source_snapshot_id="def",
                safety_snapshot_id="safety-1",
                selection_json='{"type":"world"}',
                is_rollback=False,
                started_at=started,
                finished_at=started,
                status=RestorationStatus.SUCCEEDED,
            )
        )
        await session.commit()

    with patch(
        "app.routers.servers.world_restore.get_async_session", session_factory
    ):
        flipped = await mark_running_restorations_interrupted()

    assert flipped == 1

    async with session_factory() as session:
        running_row = (
            await session.execute(
                select(Restoration).where(
                    Restoration.id == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                )
            )
        ).scalar_one()
        assert running_row.status is RestorationStatus.INTERRUPTED
        assert running_row.error_message == "server restarted before completion"
        assert running_row.finished_at is not None

        succeeded_row = (
            await session.execute(
                select(Restoration).where(
                    Restoration.id == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                )
            )
        ).scalar_one()
        assert succeeded_row.status is RestorationStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_no_running_rows_returns_zero(session_factory):
    with patch(
        "app.routers.servers.world_restore.get_async_session", session_factory
    ):
        flipped = await mark_running_restorations_interrupted()
    assert flipped == 0
