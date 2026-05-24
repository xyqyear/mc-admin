from pathlib import Path
from typing import Any, cast

import pytest
from alembic import command
from sqlalchemy import Connection, create_engine, inspect, text

from app.db import migrations
from app.models import Base


def set_database_url(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    monkeypatch.setattr(
        migrations.settings, "database_url", f"sqlite+aiosqlite:///{db_path}"
    )


def version(db_path: Path) -> str | None:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as connection:
            if not inspect(connection).has_table("alembic_version"):
                return None
            value = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
            return str(value) if value is not None else None
    finally:
        engine.dispose()


def has_table(db_path: Path, table_name: str) -> bool:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as connection:
            found = connection.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name = :table_name"
                ),
                {"table_name": table_name},
            ).scalar()
    finally:
        engine.dispose()
    return found is not None


def columns(db_path: Path, table_name: str) -> set[str]:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as connection:
            return {
                column["name"]
                for column in inspect(connection).get_columns(table_name)
            }
    finally:
        engine.dispose()


def indexes(db_path: Path, table_name: str) -> set[str]:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as connection:
            names: set[str] = set()
            for index in inspect(connection).get_indexes(table_name):
                if index["name"] is not None:
                    names.add(index["name"])
            return names
    finally:
        engine.dispose()


def schema_snapshot(db_path: Path) -> dict[str, dict[str, object]]:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            snapshot: dict[str, dict[str, object]] = {}
            table_names = sorted(
                name
                for name in inspector.get_table_names()
                if name != "alembic_version"
            )
            for table_name in table_names:
                snapshot[table_name] = {
                    "columns": tuple(
                        (
                            str(cast(dict[str, Any], column)["name"]),
                            str(cast(dict[str, Any], column)["type"]),
                            bool(cast(dict[str, Any], column)["nullable"]),
                            int(cast(dict[str, Any], column).get("primary_key", 0)),
                        )
                        for column in inspector.get_columns(table_name)
                    ),
                    "indexes": tuple(
                        sorted(
                            _index_signature(cast(dict[str, Any], index))
                            for index in inspector.get_indexes(table_name)
                        )
                    ),
                    "unique_constraints": tuple(
                        sorted(
                            _unique_constraint_signature(
                                cast(dict[str, Any], constraint)
                            )
                            for constraint in inspector.get_unique_constraints(
                                table_name
                            )
                        )
                    ),
                }
            return snapshot
    finally:
        engine.dispose()


def _index_signature(index: dict[str, Any]) -> tuple[str, tuple[str, ...], bool]:
    column_names = index.get("column_names") or ()
    return (
        str(index["name"]),
        tuple(str(column_name) for column_name in column_names),
        bool(index["unique"]),
    )


def _unique_constraint_signature(constraint: dict[str, Any]) -> tuple[str, ...]:
    column_names = constraint.get("column_names") or ()
    return tuple(str(column_name) for column_name in column_names)


def run_alembic(db_path: Path, action: str, revision: str) -> None:
    engine = create_engine(f"sqlite:///{db_path}")
    alembic_cfg = migrations._alembic_config()
    try:
        with engine.begin() as connection:
            alembic_cfg.attributes["connection"] = connection
            if action == "upgrade":
                command.upgrade(alembic_cfg, revision)
            elif action == "downgrade":
                command.downgrade(alembic_cfg, revision)
            elif action == "stamp":
                command.stamp(alembic_cfg, revision)
            else:
                raise ValueError(f"Unsupported Alembic action: {action}")
    finally:
        engine.dispose()


def create_unversioned_server_database(db_path: Path) -> None:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.begin() as connection:
            create_legacy_server_table(connection)
    finally:
        engine.dispose()


def create_legacy_server_table(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE server (
                id INTEGER NOT NULL PRIMARY KEY,
                server_id VARCHAR(100) NOT NULL,
                status VARCHAR(7) NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
    )
    connection.execute(
        text("CREATE INDEX ix_server_server_id ON server (server_id)")
    )
    connection.execute(
        text(
            """
            INSERT INTO server (server_id, status, created_at, updated_at)
            VALUES ('survival', 'ACTIVE', '2026-01-01 00:00:00', '2026-01-01 00:00:00')
            """
        )
    )


def create_current_schema_downgraded_to(db_path: Path, revision: str) -> None:
    engine = create_engine(f"sqlite:///{db_path}")
    alembic_cfg = migrations._alembic_config()
    try:
        with engine.begin() as connection:
            Base.metadata.create_all(connection)
            alembic_cfg.attributes["connection"] = connection
            command.stamp(alembic_cfg, "head")
            command.downgrade(alembic_cfg, revision)
    finally:
        engine.dispose()
