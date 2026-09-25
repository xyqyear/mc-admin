import json
import sqlite3
from contextlib import closing
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

REVISION = "2026092502"
PREVIOUS = "2026092501"


def insert_server(connection, server_id, row_id, *, created="2026-01-01", removed=None):
    connection.execute(
        "INSERT INTO server (id,server_id,status,created_at,updated_at) VALUES (?,?,?,?,?)",
        (row_id, server_id, "REMOVED" if removed else "ACTIVE", created, removed or created),
    )


def insert_job(connection, job_id, server_id, *, created="2026-02-01", updated=None, name=None, params=None, status="PAUSED"):
    connection.execute(
        "INSERT INTO cronjob (cronjob_id,identifier,name,cron,params_json,execution_count,is_system,status,created_at,updated_at) "
        "VALUES (?,'restart_server',?,'0 6 * * *',?,7,0,?,?,?)",
        (job_id, name or f"restart-{server_id}", params if params is not None else json.dumps({"server_id": server_id}),
         status, created, updated or created),
    )


def test_binding_migration_preserves_payloads_status_ids_and_execution_history(tmp_path, capsys):
    path = tmp_path / "legacy.sqlite3"
    run_alembic(path, "upgrade", PREVIOUS)
    with closing(sqlite3.connect(path)) as connection, connection:
        insert_server(connection, "survival", 10)
        insert_server(connection, "survival2", 20)
        insert_server(connection, "recreated", 30, removed="2026-03-01")
        insert_server(connection, "recreated", 31, created="2026-04-01")
        insert_server(connection, "ambiguous", 40, removed="2026-03-01")
        insert_server(connection, "ambiguous", 41, created="2026-04-01")
        insert_server(connection, "duplicate", 50)
        insert_server(connection, "before-registration", 60, created="2026-04-01")
        insert_job(connection, "exact", "survival")
        insert_job(connection, "prefix", "survival2")
        insert_job(connection, "custom", "survival", name="operator-defined-restart")
        insert_job(connection, "old-generation", "recreated")
        insert_job(connection, "spans-generations", "ambiguous", updated="2026-05-01")
        insert_job(connection, "duplicate-a", "duplicate")
        insert_job(connection, "duplicate-b", "duplicate")
        insert_job(connection, "invalid", "invalid", params="broken JSON")
        insert_job(connection, "mismatch", "mismatch", params='{"server_id":"survival"}')
        insert_job(connection, "missing", "missing")
        insert_job(connection, "too-early", "before-registration")
        connection.execute(
            "INSERT INTO cronjob_execution (cronjob_id,execution_id,started_at,status,messages_json) "
            "VALUES ('old-generation','retained-execution','2026-02-01','COMPLETED','[\"retained\"]')"
        )
        before = connection.execute("SELECT * FROM cronjob ORDER BY id").fetchall()
        history = connection.execute("SELECT * FROM cronjob_execution").fetchall()
    run_alembic(path, "upgrade", REVISION)
    report = capsys.readouterr().err
    assert "uq_cronjob_managed_binding" in indexes(path, "cronjob")
    with closing(sqlite3.connect(path)) as connection, connection:
        after = connection.execute("SELECT * FROM cronjob ORDER BY id").fetchall()
        assert [row[:len(before[0])] for row in after] == before
        assert connection.execute("SELECT * FROM cronjob_execution").fetchall() == history
        rows = {row[0]: row[1:] for row in connection.execute(
            "SELECT cronjob_id,managed_server_generation,managed_purpose,managed_binding_issue FROM cronjob"
        )}
        assert rows["exact"] == (10, "restart", None)
        assert rows["prefix"] == (20, "restart", None)
        assert rows["old-generation"] == (30, "restart", None)
        assert rows["custom"] == (None, None, None)
        for job, issue in {
            "spans-generations": "generation_uncertain", "duplicate-a": "duplicate_candidates",
            "duplicate-b": "duplicate_candidates", "invalid": "invalid_params", "mismatch": "name_params_mismatch",
            "missing": "server_missing", "too-early": "generation_uncertain",
        }.items():
            assert rows[job] == (None, "restart", issue)
            assert job in report and issue in report
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE cronjob SET managed_server_generation=10,managed_purpose='restart' WHERE cronjob_id='custom'")
    with pytest.raises(RuntimeError, match="不能删除身份保护"):
        run_alembic(path, "downgrade", PREVIOUS)
    assert version(path) == REVISION


def test_empty_binding_migration_matches_metadata_and_can_downgrade(tmp_path):
    path = tmp_path / "upgraded.sqlite3"
    run_alembic(path, "upgrade", REVISION)
    metadata = tmp_path / "metadata.sqlite3"
    create_current_schema_downgraded_to(metadata, REVISION)
    actual, expected = schema_snapshot(path)["cronjob"], schema_snapshot(metadata)["cronjob"]
    assert sorted(cast(tuple, actual.pop("columns"))) == sorted(cast(tuple, expected.pop("columns")))
    assert actual == expected
    with closing(sqlite3.connect(path)) as connection, connection:
        insert_job(connection, "custom", "survival", name="custom")
        before = connection.execute("SELECT cronjob_id,params_json,status FROM cronjob").fetchall()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE cronjob SET managed_purpose='restart'")
    run_alembic(path, "downgrade", PREVIOUS)
    assert version(path) == PREVIOUS
    assert "managed_server_generation" not in columns(path, "cronjob")
    with closing(sqlite3.connect(path)) as connection, connection:
        assert connection.execute("SELECT cronjob_id,params_json,status FROM cronjob").fetchall() == before


@pytest.mark.parametrize("created,updated", [("invalid", "2026-02-01"), ("2026-02-01", "2026-01-01")])
def test_invalid_time_evidence_is_reported_without_guessing(tmp_path, created, updated):
    path = tmp_path / "bad-evidence.sqlite3"
    run_alembic(path, "upgrade", PREVIOUS)
    with closing(sqlite3.connect(path)) as connection, connection:
        insert_server(connection, "survival", 1)
        insert_job(connection, "uncertain", "survival", created=created, updated=updated)
    run_alembic(path, "upgrade", REVISION)
    with closing(sqlite3.connect(path)) as connection, connection:
        assert connection.execute("SELECT managed_server_generation,managed_binding_issue FROM cronjob").fetchone() == (None, "generation_uncertain")


def test_distinct_historical_generations_can_keep_their_own_canonical_plan(tmp_path):
    path = tmp_path / "generations.sqlite3"
    run_alembic(path, "upgrade", PREVIOUS)
    with closing(sqlite3.connect(path)) as connection, connection:
        insert_server(connection, "survival", 10, removed="2026-03-01")
        insert_server(connection, "survival", 20, created="2026-04-01")
        insert_job(connection, "old", "survival")
        insert_job(connection, "new", "survival", created="2026-05-01")
    run_alembic(path, "upgrade", REVISION)
    with closing(sqlite3.connect(path)) as connection, connection:
        assert connection.execute(
            "SELECT cronjob_id,managed_server_generation,managed_binding_issue FROM cronjob ORDER BY id"
        ).fetchall() == [("old", 10, None), ("new", 20, None)]


def test_failed_constraint_install_rolls_back_backfill_and_preserves_historical_rows(tmp_path, monkeypatch):
    from alembic import op

    path = tmp_path / "failed-upgrade.sqlite3"
    run_alembic(path, "upgrade", PREVIOUS)
    with closing(sqlite3.connect(path)) as connection, connection:
        insert_server(connection, "survival", 1)
        insert_job(connection, "retained", "survival")
        before = connection.execute("SELECT * FROM cronjob").fetchall()
    original_create_index = op.create_index

    def fail_binding_index(name, *args, **kwargs):
        if name == "uq_cronjob_managed_binding":
            raise RuntimeError("injected index failure")
        return original_create_index(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(op, "create_index", fail_binding_index)
        with pytest.raises(RuntimeError, match="injected index failure"):
            run_alembic(path, "upgrade", REVISION)
    assert version(path) == PREVIOUS
    assert "managed_server_generation" not in columns(path, "cronjob")
    with closing(sqlite3.connect(path)) as connection, connection:
        assert connection.execute("SELECT * FROM cronjob").fetchall() == before
    run_alembic(path, "upgrade", REVISION)
    with closing(sqlite3.connect(path)) as connection, connection:
        assert connection.execute("SELECT managed_server_generation FROM cronjob").fetchone() == (1,)
