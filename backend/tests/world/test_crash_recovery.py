"""Lifespan crash recovery: any restoration row with status=running on
backend startup should flip to interrupted with an error message and a
finished_at timestamp."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.snapshots.recovery import mark_running_restorations_interrupted
from app.snapshots.restoration_models import (
    Restoration,
    RestorationStatus,
    RestorationType,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [RestorationStatus.PENDING, RestorationStatus.RUNNING])
async def test_unfinished_rows_become_interrupted(db_session_factory, status):
    started = datetime.now(UTC) - timedelta(minutes=10)
    async with db_session_factory() as session:
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
                status=status,
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

    flipped = await mark_running_restorations_interrupted()

    assert flipped == 1

    async with db_session_factory() as session:
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
async def test_no_running_rows_returns_zero(db_session_factory):
    flipped = await mark_running_restorations_interrupted()
    assert flipped == 0
