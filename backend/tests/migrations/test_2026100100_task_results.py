from pathlib import Path

from sqlalchemy import create_engine, text

from tests.migrations.helpers import columns, run_alembic, set_database_url, version

REVISION = "2026100100"
PREVIOUS = "2026093000"


def test_task_results_upgrade_and_downgrade_preserve_operation_history(tmp_path: Path, monkeypatch):
    database = tmp_path / "task-results.sqlite3"
    set_database_url(monkeypatch, database)
    run_alembic(database, "upgrade", PREVIOUS)
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO operation_journal
              (operation_id,kind,origin,name,legacy_id,resources_json,state,phase,created_at,updated_at,
               ended_at,data_changed,writers_stopped,ownership_known,processes_json,
               recovery_refs_json,has_recovery_refs,cache_degraded)
            VALUES ('retained','snapshot_create','task','backup','retained','[]','succeeded','done',
                    '2026-10-01 00:00:00','2026-10-01 00:00:00','2026-10-01 00:00:00',0,1,1,'[]','[]',0,0)
        """))
    run_alembic(database, "upgrade", REVISION)
    assert "task_result_json" in columns(database, "operation_journal")
    with engine.begin() as connection:
        assert connection.scalar(text("SELECT state FROM operation_journal WHERE operation_id='retained'")) == "succeeded"
        assert connection.scalar(text("SELECT task_result_json FROM operation_journal WHERE operation_id='retained'")) is None
        connection.execute(text("UPDATE operation_journal SET task_result_json=:result WHERE operation_id='retained'"), {"result": '{"snapshot":{"short_id":"backup"}}'})
    run_alembic(database, "downgrade", PREVIOUS)
    assert version(database) == PREVIOUS
    assert "task_result_json" not in columns(database, "operation_journal")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT state FROM operation_journal WHERE operation_id='retained'")) == "succeeded"
    engine.dispose()
