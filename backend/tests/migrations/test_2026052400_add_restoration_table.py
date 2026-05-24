from pathlib import Path

import pytest

from app.db import migrations

from .helpers import (
    columns,
    has_table,
    indexes,
    run_alembic,
    set_database_url,
    version,
)

REVISION = "2026052400"
DOWN_REVISION = "f2ee81a56fee"


async def test_startup_upgrade_and_downgrade_restoration_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "restoration.sqlite3"
    set_database_url(monkeypatch, db_path)

    run_alembic(db_path, "upgrade", DOWN_REVISION)

    assert version(db_path) == DOWN_REVISION
    assert not has_table(db_path, "restoration")

    await migrations.ensure_database_schema()

    assert version(db_path) == REVISION
    assert has_table(db_path, "restoration")
    assert {
        "id",
        "server_id",
        "type",
        "source_snapshot_id",
        "safety_snapshot_id",
        "selection_json",
        "is_rollback",
        "initiated_by_user_id",
        "started_at",
        "finished_at",
        "status",
        "error_message",
    } == columns(db_path, "restoration")
    assert "ix_restoration_server_id" in indexes(db_path, "restoration")

    run_alembic(db_path, "downgrade", DOWN_REVISION)

    assert version(db_path) == DOWN_REVISION
    assert not has_table(db_path, "restoration")
