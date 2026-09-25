import json
import sqlite3
from contextlib import closing
from typing import cast

import pytest

from .helpers import (
    columns,
    create_current_schema_downgraded_to,
    run_alembic,
    schema_snapshot,
    version,
)

REVISION = "2026092503"
PREVIOUS = "2026092502"


def insert_server(connection, row_id, name, created, removed=None):
    connection.execute(
        "INSERT INTO server (id,server_id,status,created_at,updated_at) VALUES (?,?,?,?,?)",
        (row_id, name, "REMOVED" if removed else "ACTIVE", created, removed or created),
    )


def insert_restoration(connection, row_id, server_id, started, finished: str | None = "2026-02-02", *, status="SUCCEEDED", rollback=False):
    selection = json.dumps({"type": "dimension", "region_dir_relpath": "world/region", "absent_sidecar_dirs": ["world/poi"]})
    connection.execute(
        "INSERT INTO restoration (id,server_id,type,source_snapshot_id,safety_snapshot_id,selection_json,is_rollback,"
        "initiated_by_user_id,started_at,finished_at,status,error_message) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (row_id, server_id, "DIMENSION", "source-" + row_id, "safety-" + row_id, selection, rollback, 42,
         started, finished, status, "retained diagnostic" if status != "SUCCEEDED" else None),
    )


def test_restoration_migration_preserves_history_and_binds_only_one_lifetime(tmp_path, capsys):
    database = tmp_path / "restoration.sqlite3"
    run_alembic(database, "upgrade", PREVIOUS)
    with closing(sqlite3.connect(database)) as connection, connection:
        insert_server(connection, 10, "survival", "2026-01-01", "2026-03-01")
        insert_server(connection, 20, "survival", "2026-04-01")
        insert_server(connection, 30, "overlap", "2026-01-01", "2026-06-01")
        insert_server(connection, 40, "overlap", "2026-04-01")
        insert_server(connection, 50, "only-tombstone", "2026-01-01", "2026-03-01")
        insert_restoration(connection, "old-generation", "survival", "2026-02-01")
        insert_restoration(connection, "new-generation", "survival", "2026-05-01", "2026-05-02", rollback=True)
        insert_restoration(connection, "crosses-generations", "survival", "2026-02-01", "2026-05-01", status="INTERRUPTED")
        insert_restoration(connection, "overlapping-history", "overlap", "2026-05-01", "2026-05-02")
        insert_restoration(connection, "tombstone", "only-tombstone", "2026-02-01", status="FAILED")
        insert_restoration(connection, "missing-server", "missing", "2026-02-01")
        insert_restoration(connection, "in-progress", "survival", "2026-05-01", None, status="RUNNING")
        before = connection.execute("SELECT * FROM restoration ORDER BY id").fetchall()
        servers = connection.execute("SELECT * FROM server ORDER BY id").fetchall()
    run_alembic(database, "upgrade", REVISION)
    report = capsys.readouterr().err
    with closing(sqlite3.connect(database)) as connection, connection:
        after = connection.execute("SELECT * FROM restoration ORDER BY id").fetchall()
        assert [row[:len(before[0])] for row in after] == before
        assert connection.execute("SELECT * FROM server ORDER BY id").fetchall() == servers
        bindings = {row[0]: row[1:] for row in connection.execute(
            "SELECT id,server_generation,binding_issue FROM restoration"
        )}
    assert bindings == {
        "old-generation": (10, None), "new-generation": (20, None),
        "crosses-generations": (None, "generation_uncertain"),
        "overlapping-history": (None, "generation_uncertain"),
        "tombstone": (50, None), "missing-server": (None, "server_missing"),
        "in-progress": (20, None),
    }
    for identity in ("crosses-generations", "overlapping-history", "missing-server"):
        assert identity in report
    with pytest.raises(RuntimeError, match="不能删除实例归属保护"):
        run_alembic(database, "downgrade", PREVIOUS)
    assert version(database) == REVISION
    with closing(sqlite3.connect(database)) as connection, connection:
        assert connection.execute("SELECT * FROM restoration ORDER BY id").fetchall() == after


@pytest.mark.parametrize("started,finished", [
    ("invalid", "2026-02-02"), ("2026-02-02", "2026-02-01"),
    ("2025-12-01", "2025-12-02"), ("2026-02-01", "invalid"),
])
def test_invalid_or_pre_registration_time_evidence_is_not_guessed(tmp_path, started, finished):
    database = tmp_path / "invalid.sqlite3"
    run_alembic(database, "upgrade", PREVIOUS)
    with closing(sqlite3.connect(database)) as connection, connection:
        insert_server(connection, 1, "survival", "2026-01-01")
        insert_restoration(connection, "uncertain", "survival", started, finished)
        before = connection.execute("SELECT * FROM restoration").fetchone()
    run_alembic(database, "upgrade", REVISION)
    with closing(sqlite3.connect(database)) as connection, connection:
        assert connection.execute("SELECT server_generation,binding_issue FROM restoration").fetchone() == (None, "generation_uncertain")
        assert connection.execute("SELECT * FROM restoration").fetchone()[:len(before)] == before


def test_empty_restoration_upgrade_matches_metadata_and_supports_downgrade(tmp_path):
    database = tmp_path / "upgraded.sqlite3"
    run_alembic(database, "upgrade", REVISION)
    metadata = tmp_path / "metadata.sqlite3"
    create_current_schema_downgraded_to(metadata, REVISION)
    actual = schema_snapshot(database)["restoration"]
    expected = schema_snapshot(metadata)["restoration"]
    assert sorted(cast(tuple, actual.pop("columns"))) == sorted(cast(tuple, expected.pop("columns")))
    assert actual == expected
    run_alembic(database, "downgrade", PREVIOUS)
    assert version(database) == PREVIOUS
    assert "server_generation" not in columns(database, "restoration")
    assert "binding_issue" not in columns(database, "restoration")
