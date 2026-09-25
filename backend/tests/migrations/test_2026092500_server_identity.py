import sqlite3
from contextlib import closing

import pytest

from .helpers import indexes, run_alembic, version

REVISION = "2026092500"
DOWN_REVISION = "2026092400"


def insert_server(connection, server_id, status="ACTIVE", row_id=None):
    result = connection.execute(
        "INSERT INTO server (id,server_id,status,created_at,updated_at) "
        "VALUES (?,?,?,'2026-09-25 00:00:00','2026-09-25 00:00:00')",
        (row_id, server_id, status),
    ).lastrowid
    assert result is not None
    return result


def test_identity_migration_retains_history_and_never_reuses_deleted_id(tmp_path):
    path = tmp_path / "legacy.db"
    run_alembic(path, "upgrade", DOWN_REVISION)
    with closing(sqlite3.connect(path)) as connection, connection:
        insert_server(connection, "legacy name", "REMOVED", 18)
        insert_server(connection, "legacy name", "ACTIVE", 27)
        before = connection.execute("SELECT * FROM server ORDER BY id").fetchall()
    run_alembic(path, "upgrade", REVISION)
    assert "uq_server_active_name" in indexes(path, "server")
    with closing(sqlite3.connect(path)) as connection, connection:
        assert connection.execute("SELECT * FROM server ORDER BY id").fetchall() == before
        with pytest.raises(sqlite3.IntegrityError):
            insert_server(connection, "legacy name")
        connection.execute("DELETE FROM server")
        assert insert_server(connection, "legacy name") > 27
    run_alembic(path, "downgrade", DOWN_REVISION)
    assert "uq_server_active_name" not in indexes(path, "server")
    assert version(path) == DOWN_REVISION


def test_ambiguous_legacy_active_rows_fail_before_schema_or_history_changes(tmp_path):
    path = tmp_path / "ambiguous.db"
    run_alembic(path, "upgrade", DOWN_REVISION)
    with closing(sqlite3.connect(path)) as connection, connection:
        insert_server(connection, "legacy name", row_id=1)
        insert_server(connection, "legacy name", row_id=2)
        before = connection.execute("SELECT * FROM server ORDER BY id").fetchall()
        schema_before = connection.execute("SELECT sql FROM sqlite_master WHERE name='server'").fetchone()
    with pytest.raises(RuntimeError, match="重复.*服务器"):
        run_alembic(path, "upgrade", REVISION)
    assert version(path) == DOWN_REVISION
    with closing(sqlite3.connect(path)) as connection, connection:
        assert connection.execute("SELECT * FROM server ORDER BY id").fetchall() == before
        assert connection.execute("SELECT sql FROM sqlite_master WHERE name='server'").fetchone() == schema_before
