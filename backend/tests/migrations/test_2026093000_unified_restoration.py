import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.snapshots.restoration_models import RestorationStatus
from app.snapshots.restoration_store import RestorationStore, restoration_binding_issue

from .helpers import (
    create_current_schema_downgraded_to,
    run_alembic,
    schema_snapshot,
    version,
)

REVISION = "2026093000"
PREVIOUS = "2026092503"


def seed_history(database: Path) -> list[dict]:
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/restoration-history.json").read_text()
    )
    run_alembic(database, "upgrade", fixture["revision"])
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.row_factory = sqlite3.Row
        for row in fixture["servers"]:
            connection.execute(
                "INSERT INTO server(id,server_id,status,created_at,updated_at) "
                "VALUES (:id,:server_id,:status,:created_at,:updated_at)",
                row,
            )
        for row in fixture["restorations"]:
            connection.execute(
                "INSERT INTO restoration(id,server_id,type,server_generation,binding_issue,source_snapshot_id,"
                "safety_snapshot_id,selection_json,is_rollback,initiated_by_user_id,started_at,finished_at,status,error_message) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row["id"],
                    "survival",
                    row["selection"]["type"].upper(),
                    row["generation"],
                    row.get("binding_issue"),
                    "source-" + row["id"],
                    row.get("safety_snapshot_id", "safety-" + row["id"]),
                    json.dumps(row["selection"]),
                    row.get("is_rollback", False),
                    42,
                    "2026-05-01T00:00:00",
                    None if row["status"] == "RUNNING" else "2026-05-01T00:01:00",
                    row["status"],
                    "retained evidence" if row["status"] != "SUCCEEDED" else None,
                ),
            )
        return [
            dict(row)
            for row in connection.execute("SELECT * FROM restoration ORDER BY id")
        ]


async def test_upgrade_preserves_history_and_does_not_rebind_same_name(tmp_path):
    database = tmp_path / "history.sqlite3"
    before = seed_history(database)
    assert {row["status"] for row in before} == {
        "SUCCEEDED",
        "FAILED",
        "INTERRUPTED",
        "RUNNING",
    }
    run_alembic(database, "upgrade", REVISION)
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        for old in before:
            row = connection.execute(
                "SELECT * FROM restoration WHERE id=?", (old["id"],)
            ).fetchone()
            assert {key: row[key] for key in old} == old
            assert json.loads(row["targets_json"]) == [
                {"server_id": "survival", "generation": old["server_generation"]}
            ]
            scope = json.loads(row["scope_json"])
            assert scope["version"] == 1
            assert scope["scope"]["kind"] == "world"
            assert scope["scope"]["selection"]["type"] == old["type"].lower()
            assert row["operation_id"] is None
            assert row["rollback_of_id"] is None
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    store = RestorationStore(async_sessionmaker(engine, expire_on_commit=False))
    try:
        old = await store.get("old-world")
        assert (
            old is not None
            and restoration_binding_issue(old, 20) == "generation_changed"
        )
        uncertain = await store.get("uncertain")
        assert (
            uncertain is not None
            and restoration_binding_issue(uncertain, 20) == "generation_uncertain"
        )
        missing = await store.get("missing-safety")
        assert missing is not None and missing.safety_snapshot_id is None
        assert await store.interrupt_running() == 1
        running = await store.get("running")
        assert running is not None and running.status is RestorationStatus.INTERRUPTED
        assert running.safety_snapshot_id == "safety-running"
        complete = await store.get("current-dimension")
        assert complete is not None and complete.status is RestorationStatus.SUCCEEDED
    finally:
        await engine.dispose()


def test_retained_history_prevents_destructive_schema_downgrade(tmp_path):
    database = tmp_path / "retained.sqlite3"
    seed_history(database)
    run_alembic(database, "upgrade", REVISION)
    with pytest.raises(RuntimeError, match="不能删除统一恢复证据"):
        run_alembic(database, "downgrade", PREVIOUS)
    assert version(database) == REVISION


def test_empty_upgrade_matches_metadata_and_downgrades(tmp_path):
    database, metadata = tmp_path / "upgrade.sqlite3", tmp_path / "metadata.sqlite3"
    run_alembic(database, "upgrade", REVISION)
    create_current_schema_downgraded_to(metadata, REVISION)
    actual, expected = (
        schema_snapshot(database)["restoration"],
        schema_snapshot(metadata)["restoration"],
    )
    assert sorted(cast(list, actual.pop("columns"))) == sorted(
        cast(list, expected.pop("columns"))
    )
    assert actual == expected
    run_alembic(database, "downgrade", PREVIOUS)
    assert version(database) == PREVIOUS


def test_operation_identity_is_unique_without_limiting_legacy_rows(tmp_path):
    database = tmp_path / "unique.sqlite3"
    seed_history(database)
    run_alembic(database, "upgrade", REVISION)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "UPDATE restoration SET operation_id='operation' WHERE id='old-world'"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE restoration SET operation_id='operation' WHERE id='current-dimension'"
            )


def test_failed_backfill_rolls_back_schema_and_allows_retry(tmp_path, monkeypatch):
    database = tmp_path / "failed-upgrade.sqlite3"
    before = seed_history(database)
    before_schema = schema_snapshot(database)
    execute = Connection.execute

    def fail_backfill(connection, statement, *args, **kwargs):
        if str(statement).startswith("UPDATE restoration SET scope_json="):
            raise RuntimeError("injected backfill failure")
        return execute(connection, statement, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "execute", fail_backfill)
        with pytest.raises(RuntimeError, match="injected backfill failure"):
            run_alembic(database, "upgrade", REVISION)
    assert version(database) == PREVIOUS
    assert schema_snapshot(database) == before_schema
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        assert [
            dict(row)
            for row in connection.execute("SELECT * FROM restoration ORDER BY id")
        ] == before
    run_alembic(database, "upgrade", REVISION)
    assert version(database) == REVISION
