from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.migrations.helpers import (
    has_table,
    run_alembic,
    schema_snapshot,
    set_database_url,
    version,
)

REVISION = "2026100600"
PREVIOUS = "2026100100"


def test_note_migration_is_additive_and_preserves_existing_task_results(tmp_path: Path, monkeypatch):
    database = tmp_path / "notes.sqlite3"
    set_database_url(monkeypatch, database)
    run_alembic(database, "upgrade", PREVIOUS)
    original = schema_snapshot(database)
    engine = create_engine(f"sqlite:///{database}")
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO operation_journal
                  (operation_id,kind,origin,name,legacy_id,resources_json,state,phase,created_at,updated_at,
                   ended_at,data_changed,writers_stopped,ownership_known,processes_json,
                   recovery_refs_json,has_recovery_refs,cache_degraded,task_result_json)
                VALUES ('retained','snapshot_create','task','backup','retained','[]','succeeded','done',
                        '2026-10-01 00:00:00','2026-10-01 00:00:00','2026-10-01 00:00:00',0,1,1,'[]','[]',0,0,
                        '{"snapshot":{"id":"retained-snapshot"}}')
            """))
        run_alembic(database, "upgrade", REVISION)
        assert version(database) == REVISION and has_table(database, "snapshot_notes")
        upgraded = schema_snapshot(database)
        upgraded.pop("snapshot_notes")
        assert upgraded == original
        with engine.begin() as connection:
            assert connection.scalar(text("SELECT task_result_json FROM operation_journal WHERE operation_id='retained'")) == '{"snapshot":{"id":"retained-snapshot"}}'
            connection.execute(text("INSERT INTO snapshot_notes VALUES (:repository, :snapshot, :note)"), {"repository": "a" * 64, "snapshot": "b" * 64, "note": "升级前的中文备注"})
        run_alembic(database, "downgrade", PREVIOUS)
        assert version(database) == PREVIOUS and not has_table(database, "snapshot_notes")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT task_result_json FROM operation_journal WHERE operation_id='retained'")) == '{"snapshot":{"id":"retained-snapshot"}}'
    finally:
        engine.dispose()


def test_note_schema_enforces_repository_identity_and_character_limit(tmp_path: Path, monkeypatch):
    database = tmp_path / "notes.sqlite3"
    set_database_url(monkeypatch, database)
    run_alembic(database, "upgrade", REVISION)
    engine = create_engine(f"sqlite:///{database}")
    try:
        insert = text("INSERT INTO snapshot_notes VALUES (:repository, :snapshot, :note)")
        with engine.begin() as connection:
            connection.execute(insert, {"repository": "a" * 64, "snapshot": "b" * 64, "note": "😀" * 500})
            connection.execute(insert, {"repository": "c" * 64, "snapshot": "b" * 64, "note": "另一仓库"})
        for values in (
            {"repository": "a" * 64, "snapshot": "b" * 64, "note": "重复身份"},
            {"repository": "a" * 64, "snapshot": "d" * 64, "note": "字" * 501},
        ):
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(insert, values)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT COUNT(*) FROM snapshot_notes")) == 2
    finally:
        engine.dispose()
