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

REVISION = "2026060500"
DOWN_REVISION = "2026052400"


async def test_startup_upgrade_and_downgrade_self_check_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "self_check.sqlite3"
    set_database_url(monkeypatch, db_path)

    run_alembic(db_path, "upgrade", DOWN_REVISION)

    assert version(db_path) == DOWN_REVISION
    assert "is_system" not in columns(db_path, "cronjob")
    assert not has_table(db_path, "self_check_run")
    assert not has_table(db_path, "self_check_finding")

    await migrations.ensure_database_schema()

    assert version(db_path) == REVISION
    assert "is_system" in columns(db_path, "cronjob")
    assert has_table(db_path, "self_check_run")
    assert {
        "id",
        "trigger",
        "scope",
        "check_id",
        "status",
        "started_at",
        "finished_at",
        "summary_json",
        "requested_by_user_id",
        "error_message",
    } == columns(db_path, "self_check_run")
    assert {
        "ix_self_check_run_finished_at",
        "idx_self_check_run_scope_finished_id",
        "idx_self_check_run_scope_check_finished_id",
    }.issubset(indexes(db_path, "self_check_run"))

    assert has_table(db_path, "self_check_finding")
    assert {
        "id",
        "run_id",
        "check_id",
        "category",
        "severity",
        "status",
        "server_id",
        "title",
        "message",
        "evidence_json",
        "remediation_json",
        "created_at",
    } == columns(db_path, "self_check_finding")
    assert {
        "idx_self_check_finding_run",
    }.issubset(indexes(db_path, "self_check_finding"))

    run_alembic(db_path, "downgrade", DOWN_REVISION)

    assert version(db_path) == DOWN_REVISION
    assert "is_system" not in columns(db_path, "cronjob")
    assert not has_table(db_path, "self_check_run")
    assert not has_table(db_path, "self_check_finding")
