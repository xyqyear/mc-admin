from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from tests.migrations.helpers import (
    columns,
    create_current_schema_downgraded_to,
    has_table,
    indexes,
    run_alembic,
    schema_snapshot,
    set_database_url,
    version,
)

REVISION = "2026092501"
PREVIOUS = "2026092500"


def test_operation_journal_upgrade_matches_metadata_and_preserves_existing_data(tmp_path: Path, monkeypatch):
    database = tmp_path / "upgrade.sqlite3"
    set_database_url(monkeypatch, database)
    run_alembic(database, "upgrade", PREVIOUS)
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO player_chat_message VALUES (901,1,1,'retained-history','2026-09-25 00:00:00')"))
    run_alembic(database, "upgrade", REVISION)
    assert {"resources_json", "processes_json", "actor_id", "phase", "state", "recovery_refs_json", "ownership_known", "writers_stopped"} <= columns(database, "operation_journal")
    assert {"ix_operation_journal_state_updated", "ix_operation_journal_retention"} <= indexes(database, "operation_journal")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT message_text FROM player_chat_message WHERE message_id=901")) == "retained-history"
    engine.dispose()
    metadata = tmp_path / "metadata.sqlite3"
    create_current_schema_downgraded_to(metadata, REVISION)
    assert schema_snapshot(database)["operation_journal"] == schema_snapshot(metadata)["operation_journal"]
    run_alembic(database, "downgrade", PREVIOUS)
    assert not has_table(database, "operation_journal")
    assert version(database) == PREVIOUS


@pytest.mark.parametrize("protected", ["active", "unknown", "reference", "blocked", "cache"])
def test_downgrade_refuses_to_discard_recovery_evidence(tmp_path: Path, monkeypatch, protected):
    database = tmp_path / "protected.sqlite3"
    set_database_url(monkeypatch, database)
    run_alembic(database, "upgrade", REVISION)
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO operation_journal
              (operation_id,kind,origin,name,resources_json,state,phase,created_at,updated_at,
               ended_at,data_changed,writers_stopped,ownership_known,processes_json,
               recovery_refs_json,has_recovery_refs,blocked_reason,cache_degraded)
            VALUES
              ('owned','world_restore','request','test','[]',:state,'writing','2026-09-25 00:00:00',
               '2026-09-25 00:00:00','2026-09-25 00:00:00',1,:stopped,0,'[]',
               '[]',:refs,:blocked,:cache)
        """), {"state": "running" if protected == "active" else "interrupted",
                 "stopped": protected != "unknown", "refs": protected == "reference",
                 "blocked": "writers_unconfirmed" if protected == "blocked" else None,
                 "cache": protected == "cache"})
    with pytest.raises(RuntimeError, match="拒绝删除操作日志"):
        run_alembic(database, "downgrade", PREVIOUS)
    assert version(database) == REVISION
    assert has_table(database, "operation_journal")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM operation_journal")) == 1
    engine.dispose()
