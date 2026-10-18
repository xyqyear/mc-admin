from pathlib import Path

from sqlalchemy import create_engine, text

from tests.migrations.helpers import columns, run_alembic, set_database_url, version

REVISION = "2026101800"
PREVIOUS = "2026100700"


def test_safe_failure_upgrade_and_downgrade_preserve_results_and_recovery(tmp_path: Path, monkeypatch):
    database = tmp_path / "task-failures.sqlite3"
    set_database_url(monkeypatch, database)
    run_alembic(database, "upgrade", PREVIOUS)
    engine = create_engine(f"sqlite:///{database}")
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO operation_journal
                  (operation_id,kind,origin,name,legacy_id,resources_json,state,phase,created_at,updated_at,
                   ended_at,data_changed,writers_stopped,ownership_known,processes_json,
                   recovery_refs_json,has_recovery_refs,cache_degraded,task_result_json,failure_code)
                VALUES ('retained','snapshot_restore','task','恢复快照','retained','[]','failed','restore',
                        '2026-10-18 00:00:00','2026-10-18 00:00:00','2026-10-18 00:00:00',1,1,1,'[]',
                        :references,1,0,:result,'restore_failed')
            """), {"references": '[{"kind":"safety_snapshot","value":"safety","resolved":false}]', "result": '{"partial":true}'})
        run_alembic(database, "upgrade", REVISION)
        assert "failure_message" in columns(database, "operation_journal")
        with engine.begin() as connection:
            assert connection.scalar(text("SELECT failure_message FROM operation_journal")) is None
            connection.execute(text("UPDATE operation_journal SET failure_message=:message"), {"message": "目标文件正在使用，请稍后重试"})
            assert connection.scalar(text("SELECT failure_message FROM operation_journal")) == "目标文件正在使用，请稍后重试"
        run_alembic(database, "downgrade", PREVIOUS)
        assert version(database) == PREVIOUS
        assert "failure_message" not in columns(database, "operation_journal")
        with engine.connect() as connection:
            row = connection.execute(text("SELECT state,task_result_json,recovery_refs_json,failure_code FROM operation_journal")).one()
            assert row == ("failed", '{"partial":true}', '[{"kind":"safety_snapshot","value":"safety","resolved":false}]', "restore_failed")
    finally:
        engine.dispose()
