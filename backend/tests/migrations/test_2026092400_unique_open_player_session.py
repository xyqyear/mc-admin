import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.db.session_repair import apply_reviewed_report, preview

from .helpers import indexes, run_alembic, version

REVISION = "2026092400"
DOWN_REVISION = "2026090700"


def legacy_database(path: Path, *, duplicates: bool) -> None:
    run_alembic(path, "upgrade", DOWN_REVISION)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executemany(
            "INSERT INTO player_session VALUES (?, 7, 8, ?, ?, ?)",
            [
                (9, "2026-09-24 11:00:00", "2026-09-24 11:00:30", 30),
                (10, "2026-09-24 12:00:00", None, None),
                *([
                    (12, "2026-09-24 12:00:20", None, None),
                    (13, "2026-09-24 12:00:00", None, None),
                ] if duplicates else []),
            ],
        )
        connection.execute(
            "INSERT INTO player_session VALUES (20, 70, 80, '2026-09-24 12:00:00', NULL, NULL)"
        )


def session_rows(path: Path):
    with closing(sqlite3.connect(path)) as connection, connection:
        return connection.execute("SELECT * FROM player_session ORDER BY session_id").fetchall()


def test_unique_session_migration_rejects_duplicates_without_mutating_history(tmp_path):
    path = tmp_path / "legacy.db"
    legacy_database(path, duplicates=True)
    before = session_rows(path)
    with pytest.raises(RuntimeError, match="重复未结束玩家会话"):
        run_alembic(path, "upgrade", REVISION)
    assert version(path) == DOWN_REVISION
    assert "uq_player_session_open" not in indexes(path, "player_session")
    assert session_rows(path) == before


def test_reviewed_repair_on_copy_retains_ids_evidence_and_exact_duration(tmp_path):
    source = tmp_path / "historical.db"
    path = tmp_path / "disposable-copy.db"
    legacy_database(source, duplicates=True)
    before = session_rows(source)
    shutil.copy2(source, path)
    evidence = tmp_path / "reviewed-repair.json"
    with closing(sqlite3.connect(path)) as connection, connection:
        report = preview(connection)
        assert report == json.loads(
            (Path(__file__).parent / "fixtures/duplicate-open-session-repair.json").read_text()
        )
        assert report["groups"][0]["canonical"]["session_id"] == 10
        assert {change["before"]["session_id"] for change in report["groups"][0]["changes"]} == {12, 13}
        applied = apply_reviewed_report(connection, report, evidence)
    assert session_rows(source) == before
    assert json.loads(evidence.read_text())["report"] == report
    assert json.loads(evidence.with_name(evidence.name + ".committed").read_text()) == applied
    repaired = session_rows(path)
    assert [row[0] for row in repaired] == [row[0] for row in before]
    assert repaired[0] == before[0]
    assert repaired[1] == before[1]
    assert repaired[-1] == before[-1]
    for row in repaired[2:4]:
        assert row[4] == row[3]
        assert row[5] == 0
    run_alembic(path, "upgrade", REVISION)
    assert "uq_player_session_open" in indexes(path, "player_session")
    engine = create_engine(f"sqlite:///{path}")
    try:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO player_session (player_db_id, server_db_id, joined_at) "
                "VALUES (7, 8, '2026-09-24 12:01:00')"
            ))
        with engine.begin() as connection:
            connection.execute(text(
                "UPDATE player_session SET left_at='2026-09-24 12:01:00', duration_seconds=60 WHERE session_id=10"
            ))
            assert connection.execute(text(
                "SELECT SUM(duration_seconds) FROM player_session WHERE player_db_id=7 AND server_db_id=8"
            )).scalar_one() == 90
    finally:
        engine.dispose()
    after = session_rows(path)
    run_alembic(path, "downgrade", DOWN_REVISION)
    assert session_rows(path) == after
    assert "uq_player_session_open" not in indexes(path, "player_session")
    assert json.loads(evidence.with_name(evidence.name + ".committed").read_text()) == applied


def test_stale_report_is_rejected_without_changes(tmp_path):
    path = tmp_path / "legacy.db"
    legacy_database(path, duplicates=True)
    with closing(sqlite3.connect(path)) as connection, connection:
        report = preview(connection)
        connection.execute("UPDATE player_session SET joined_at='2026-09-24 12:00:25' WHERE session_id=12")
        connection.commit()
        before = session_rows(path)
        with pytest.raises(ValueError, match="已变化"):
            apply_reviewed_report(connection, report, tmp_path / "evidence.json")
    assert session_rows(path) == before
    assert not (tmp_path / "evidence.json").exists()


def test_repair_failure_rolls_back_all_updates_and_retains_prepared_evidence(tmp_path):
    path = tmp_path / "legacy.db"
    legacy_database(path, duplicates=True)
    before = session_rows(path)
    evidence = tmp_path / "failed-repair.json"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            "CREATE TRIGGER fail_repair BEFORE UPDATE ON player_session "
            "WHEN OLD.session_id=12 BEGIN SELECT RAISE(ABORT, 'injected repair failure'); END"
        )
        connection.commit()
        report = preview(connection)
        with pytest.raises(sqlite3.IntegrityError, match="injected repair failure"):
            apply_reviewed_report(connection, report, evidence)
    assert session_rows(path) == before
    assert json.loads(evidence.read_text())["status"] == "prepared"
    assert not evidence.with_name(evidence.name + ".committed").exists()


def test_clean_migration_round_trip_preserves_rows(tmp_path):
    path = tmp_path / "clean.db"
    legacy_database(path, duplicates=False)
    before = session_rows(path)
    run_alembic(path, "upgrade", REVISION)
    assert version(path) == REVISION
    assert "uq_player_session_open" in indexes(path, "player_session")
    run_alembic(path, "downgrade", DOWN_REVISION)
    assert session_rows(path) == before
