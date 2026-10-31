"""Persisted legacy restoration and selection compatibility."""

import json

import pytest
from sqlalchemy import select

from app.snapshots.restoration_models import (
    Restoration,
    RestorationStatus,
    RestorationType,
)
from app.snapshots.selection_models import RestorationSelection


@pytest.mark.asyncio
async def test_restoration_round_trip(db_session_factory):
    selection = RestorationSelection(
        type=RestorationType.CHUNKS,
        region_dir_relpath="world/region",
        regions=[],
        chunks=[(10, 20), (-3, 4)],
    )
    rest_id = "abcd1234" * 4
    async with db_session_factory() as session:
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

    async with db_session_factory() as session:
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
