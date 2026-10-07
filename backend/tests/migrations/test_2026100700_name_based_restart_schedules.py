import json
import sqlite3
from contextlib import closing, contextmanager
from typing import cast

import pytest

from .helpers import (
    columns,
    create_current_schema_downgraded_to,
    indexes,
    run_alembic,
    schema_snapshot,
    version,
)

REVISION = "2026100700"
PREVIOUS = "2026100600"


def seed_retained_plans(connection):
    connection.execute(
        "INSERT INTO server (id,server_id,status,created_at,updated_at) "
        "VALUES (1,'survival','REMOVED','2025-01-01','2026-01-01'),"
        "(2,'survival','ACTIVE','2026-01-02','2026-01-02')"
    )
    for job_id, name, status, generation, purpose, issue in (
        ("old", "renamed plan", "PAUSED", 1, "restart", None),
        ("duplicate-a", "restart-survival-1", "ACTIVE", None, "restart", "duplicate_candidates"),
        ("duplicate-b", "restart-survival-2", "ACTIVE", None, "restart", "name_params_mismatch"),
        ("cancelled", "restart-survival", "CANCELLED", None, "restart", "generation_uncertain"),
        ("custom", "custom restart", "ACTIVE", None, None, None),
    ):
        connection.execute(
            "INSERT INTO cronjob (cronjob_id,identifier,name,cron,params_json,execution_count,is_system,status,"
            "created_at,updated_at,managed_server_generation,managed_purpose,managed_binding_issue) "
            "VALUES (?,'restart_server',?,'0 6 * * *',?,7,0,?,'2025-02-01','2026-02-01',?,?,?)",
            (job_id, name, json.dumps({"server_id": "survival"}), status, generation, purpose, issue),
        )
    connection.execute(
        "INSERT INTO cronjob_execution (cronjob_id,execution_id,started_at,status,messages_json) "
        "VALUES ('old','retained-execution','2025-02-01','COMPLETED','[\"retained\"]')"
    )


def retained_rows(connection):
    return {
        "cronjob": connection.execute(
            "SELECT id,cronjob_id,identifier,name,cron,second,params_json,execution_count,is_system,status,"
            "created_at,updated_at,managed_purpose FROM cronjob ORDER BY id"
        ).fetchall(),
        "cronjob_execution": connection.execute("SELECT * FROM cronjob_execution ORDER BY id").fetchall(),
        "server": connection.execute("SELECT * FROM server ORDER BY id").fetchall(),
    }


def test_upgrade_removes_binding_without_changing_plans_or_history(tmp_path):
    path = tmp_path / "retained.sqlite3"
    run_alembic(path, "upgrade", PREVIOUS)
    with closing(sqlite3.connect(path)) as connection, connection:
        seed_retained_plans(connection)
        before = retained_rows(connection)
    run_alembic(path, "upgrade", REVISION)
    assert version(path) == REVISION
    assert {"managed_server_generation", "managed_binding_issue"}.isdisjoint(columns(path, "cronjob"))
    assert "managed_purpose" in columns(path, "cronjob")
    assert "uq_cronjob_managed_binding" not in indexes(path, "cronjob")
    with closing(sqlite3.connect(path)) as connection, connection:
        assert retained_rows(connection) == before
        assert "ck_cronjob_managed_binding" not in connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='cronjob'"
        ).fetchone()[0]
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        connection.execute(
            "INSERT INTO cronjob (cronjob_id,identifier,name,cron,params_json,execution_count,is_system,status,"
            "created_at,updated_at,managed_purpose) "
            "VALUES ('new','restart_server','any name','0 7 * * *','{\"server_id\":\"survival\"}',"
            "0,0,'ACTIVE','2026-02-01','2026-02-01','restart')"
        )
    with pytest.raises(RuntimeError, match="不能恢复实例绑定"):
        run_alembic(path, "downgrade", PREVIOUS)
    assert version(path) == REVISION


def test_empty_schema_matches_metadata_and_unmanaged_jobs_can_downgrade(tmp_path):
    path = tmp_path / "upgraded.sqlite3"
    run_alembic(path, "upgrade", REVISION)
    metadata = tmp_path / "metadata.sqlite3"
    create_current_schema_downgraded_to(metadata, REVISION)
    actual, expected = schema_snapshot(path)["cronjob"], schema_snapshot(metadata)["cronjob"]
    assert sorted(cast(tuple, actual.pop("columns"))) == sorted(cast(tuple, expected.pop("columns")))
    assert actual == expected
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            "INSERT INTO cronjob (cronjob_id,identifier,name,cron,params_json,execution_count,is_system,status,"
            "created_at,updated_at) "
            "VALUES ('custom','restart_server','custom','0 6 * * *','{\"server_id\":\"survival\"}',"
            "3,0,'PAUSED','2026-01-01','2026-01-01')"
        )
        before = retained_rows(connection)
    run_alembic(path, "downgrade", PREVIOUS)
    assert version(path) == PREVIOUS
    assert {"managed_server_generation", "managed_binding_issue"}.issubset(columns(path, "cronjob"))
    assert "uq_cronjob_managed_binding" in indexes(path, "cronjob")
    with closing(sqlite3.connect(path)) as connection:
        assert retained_rows(connection) == before
        assert connection.execute(
            "SELECT managed_server_generation,managed_binding_issue FROM cronjob"
        ).fetchall() == [(None, None)]
    run_alembic(path, "upgrade", REVISION)
    with closing(sqlite3.connect(path)) as connection:
        assert retained_rows(connection) == before


def test_failed_upgrade_rolls_back_replaced_table_and_can_retry(tmp_path, monkeypatch):
    from alembic import op

    path = tmp_path / "failed.sqlite3"
    run_alembic(path, "upgrade", PREVIOUS)
    with closing(sqlite3.connect(path)) as connection, connection:
        seed_retained_plans(connection)
        before = connection.execute("SELECT * FROM cronjob ORDER BY id").fetchall()
    original_batch = op.batch_alter_table

    @contextmanager
    def fail_after_replacement(*args, **kwargs):
        with original_batch(*args, **kwargs) as batch:
            yield batch
        raise RuntimeError("injected replacement failure")

    with monkeypatch.context() as patch:
        patch.setattr(op, "batch_alter_table", fail_after_replacement)
        with pytest.raises(RuntimeError, match="injected replacement failure"):
            run_alembic(path, "upgrade", REVISION)
    assert version(path) == PREVIOUS
    assert "uq_cronjob_managed_binding" in indexes(path, "cronjob")
    assert {"managed_server_generation", "managed_binding_issue"}.issubset(columns(path, "cronjob"))
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT * FROM cronjob ORDER BY id").fetchall() == before
    run_alembic(path, "upgrade", REVISION)
    assert version(path) == REVISION
