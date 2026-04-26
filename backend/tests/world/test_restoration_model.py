"""Tests for the Restoration model + RestorationSelection round-trip."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import (
    Base,
    Restoration,
    RestorationSelection,
    RestorationStatus,
    RestorationType,
)


@pytest.fixture
async def session_maker():
    with tempfile.TemporaryDirectory(prefix="restoration_db_") as tmp:
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
async def test_restoration_round_trip(session_maker):
    selection = RestorationSelection(
        type=RestorationType.CHUNKS,
        region_dir_relpath="world/region",
        regions=[],
        chunks=[(10, 20), (-3, 4)],
    )
    rest_id = "abcd1234" * 4
    async with session_maker() as session:
        session.add(
            Restoration(
                id=rest_id,
                server_id="srv1",
                type=RestorationType.CHUNKS,
                source_snapshot_id="snap-source",
                safety_snapshot_id="snap-safety",
                selection_json=selection.model_dump_json(),
                is_rollback=False,
                initiated_by_user_id=7,
            )
        )
        await session.commit()

    async with session_maker() as session:
        loaded = (
            await session.execute(select(Restoration).where(Restoration.id == rest_id))
        ).scalar_one()
        assert loaded.server_id == "srv1"
        assert loaded.type is RestorationType.CHUNKS
        assert loaded.source_snapshot_id == "snap-source"
        assert loaded.safety_snapshot_id == "snap-safety"
        assert loaded.is_rollback is False
        assert loaded.initiated_by_user_id == 7
        assert loaded.status is RestorationStatus.RUNNING
        assert loaded.finished_at is None
        assert loaded.started_at.tzinfo is not None

        round_tripped = RestorationSelection.model_validate_json(loaded.selection_json)
        assert round_tripped.type is RestorationType.CHUNKS
        assert round_tripped.chunks == [(10, 20), (-3, 4)]


@pytest.mark.asyncio
async def test_restoration_terminal_state_update(session_maker):
    rest_id = "ee" * 16
    selection = RestorationSelection(
        type=RestorationType.WORLD,
    )
    async with session_maker() as session:
        session.add(
            Restoration(
                id=rest_id,
                server_id="srv2",
                type=RestorationType.WORLD,
                source_snapshot_id="src",
                safety_snapshot_id=None,
                selection_json=selection.model_dump_json(),
            )
        )
        await session.commit()

    async with session_maker() as session:
        row = (
            await session.execute(select(Restoration).where(Restoration.id == rest_id))
        ).scalar_one()
        row.status = RestorationStatus.SUCCEEDED
        row.finished_at = datetime.now(timezone.utc)
        await session.commit()

    async with session_maker() as session:
        row = (
            await session.execute(select(Restoration).where(Restoration.id == rest_id))
        ).scalar_one()
        assert row.status is RestorationStatus.SUCCEEDED
        assert row.finished_at is not None


@pytest.mark.asyncio
async def test_restoration_rollback_record(session_maker):
    parent_id = "ab" * 16
    rollback_id = "cd" * 16
    selection = RestorationSelection(
        type=RestorationType.REGIONS,
        region_dir_relpath="world/region",
        regions=[(0, 0), (1, 1)],
    )

    async with session_maker() as session:
        session.add(
            Restoration(
                id=parent_id,
                server_id="srv3",
                type=RestorationType.REGIONS,
                source_snapshot_id="snap-source",
                safety_snapshot_id="snap-safety",
                selection_json=selection.model_dump_json(),
                status=RestorationStatus.SUCCEEDED,
                finished_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            Restoration(
                id=rollback_id,
                server_id="srv3",
                type=RestorationType.REGIONS,
                # Rollback uses the prior safety snapshot as its source
                source_snapshot_id="snap-safety",
                safety_snapshot_id=None,
                selection_json=selection.model_dump_json(),
                is_rollback=True,
            )
        )
        await session.commit()

    async with session_maker() as session:
        rows = (
            await session.execute(
                select(Restoration).where(Restoration.server_id == "srv3").order_by(
                    Restoration.started_at
                )
            )
        ).scalars().all()
        assert [r.is_rollback for r in rows] == [False, True]
        assert rows[1].source_snapshot_id == "snap-safety"


def test_restoration_selection_json_keys():
    selection = RestorationSelection(
        type=RestorationType.DIMENSION,
        region_dir_relpath="world/DIM-1/region",
    )
    payload = json.loads(selection.model_dump_json())
    assert payload["type"] == "dimension"
    assert payload["region_dir_relpath"] == "world/DIM-1/region"
    assert payload["regions"] == []
    assert payload["chunks"] == []
    assert "world_root_name" not in payload
    assert "dimension_label" not in payload
