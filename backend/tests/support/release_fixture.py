"""Regenerate a synthetic database with the model and startup code of a pinned release."""

import argparse
import asyncio
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from contextlib import closing
from pathlib import Path

RELEASE = "v5.3.0"
COMMIT = "da30f4b033a386dc97ea72254e3ec0a4b0bdab1f"
REPOSITORY = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parents[1] / "contracts/fixtures/releases"
STAMP = "2026-09-01 00:00:00"


def seed(path: Path) -> None:
    from app.db.migrations import ensure_database_schema

    asyncio.run(ensure_database_schema())
    template = "services:\n  mc:\n    image: itzg/minecraft-server:java25\n    container_name: mc-${SERVER_NAME}\n    ports: ['25565:25565', '25575:25575']\n    environment: {VERSION: '1.21.11', SERVER_PORT: '25565'}\n"
    snapshot = json.dumps({"template_id": 201, "template_name": "synthetic-template", "yaml_template": template,
                           "variable_definitions": [], "snapshot_time": "2026-09-01T00:00:00+00:00"})
    rows = {
        "user": [{"id": 11, "username": "synthetic-owner", "hashed_password": "not-a-valid-password-hash",
                  "role": "OWNER", "created_at": STAMP}],
        "server_template": [{"id": 201, "name": "synthetic-template", "description": "Synthetic release fixture",
                             "yaml_template": template, "variable_definitions_json": "[]", "created_at": STAMP, "updated_at": STAMP}],
        "server": [{"id": identity, "server_id": name, "status": status, "template_id": 201,
                    "template_snapshot_json": snapshot, "variable_values_json": '{"SERVER_NAME":"synthetic-survival"}',
                    "created_at": STAMP, "updated_at": STAMP}
                   for identity, name, status in [(101, "synthetic-survival", "ACTIVE"), (102, "synthetic-retired", "REMOVED")]],
        "player": [{"player_db_id": 301, "uuid": "123456781234423482341234567890ab", "current_name": "FixturePlayer",
                    "skin_data": None, "avatar_data": None, "last_skin_update": None, "created_at": STAMP}],
        "player_session": [{"session_id": identity, "player_db_id": 301, "server_db_id": 101,
                            "joined_at": STAMP, "left_at": ended, "duration_seconds": duration}
                           for identity, ended, duration in [(401, "2026-09-01 00:01:00", 60), (402, None, None)]],
        "player_chat_message": [{"message_id": 501, "player_db_id": 301, "server_db_id": 101,
                                 "message_text": "Synthetic retained chat", "sent_at": STAMP}],
        "player_achievement": [{"achievement_id": 601, "player_db_id": 301, "server_db_id": 101,
                                "achievement_name": "minecraft:story/root", "earned_at": STAMP}],
        "cronjob": [{"id": 701, "cronjob_id": "synthetic-restart", "identifier": "server_restart",
                     "name": "restart-synthetic-survival", "cron": "0 5 * * *", "second": None,
                     "params_json": '{"server_id":"synthetic-survival"}', "execution_count": 1,
                     "is_system": 0, "status": "PAUSED", "created_at": STAMP, "updated_at": STAMP}],
        "cronjob_execution": [{"id": 801, "cronjob_id": "synthetic-restart", "execution_id": "synthetic-execution",
                               "started_at": STAMP, "ended_at": "2026-09-01 00:00:01", "duration_ms": 1000,
                               "status": "COMPLETED", "messages_json": '["Synthetic completed restart"]'}],
        "restoration": [{"id": "a" * 32, "server_id": "synthetic-survival", "type": "WORLD",
                         "source_snapshot_id": "1" * 64, "safety_snapshot_id": "2" * 64,
                         "selection_json": '{"type":"world","world":"world"}', "is_rollback": 0,
                         "initiated_by_user_id": 11, "started_at": STAMP, "finished_at": "2026-09-01 00:00:02",
                         "status": "SUCCEEDED", "error_message": None}],
        "dynamic_config": [{"id": 901, "module_name": "world", "config_data": '{"dimension_labels":{".":"Synthetic world"}}',
                            "config_schema_version": "1.0.0", "updated_at": STAMP}],
    }
    with closing(sqlite3.connect(path)) as connection, connection:
        for table, records in rows.items():
            for record in records:
                columns = ",".join(f'"{column}"' for column in record)
                values = ",".join("?" for _ in record)
                connection.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({values})', tuple(record.values()))


def generate() -> None:
    identity = subprocess.check_output(["git", "rev-list", "-n", "1", RELEASE], cwd=REPOSITORY, text=True).strip()
    if identity != COMMIT:
        raise RuntimeError("Release tag identity differs from the reviewed fixture source")
    archive = subprocess.check_output(["git", "archive", COMMIT, "backend"], cwd=REPOSITORY)
    with tempfile.TemporaryDirectory(prefix="mc-admin-release-fixture-") as directory:
        root = Path(directory)
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            source.extractall(root, filter="data")
        backend = root / "backend"
        database = root / "release.sqlite3"
        config = root / "empty.toml"
        config.write_text("")
        environment = dict(os.environ)
        for key in list(environment):
            if key in {"RESTIC", "JWT", "AUDIT"} or key.startswith(("RESTIC__", "JWT__", "AUDIT__")):
                del environment[key]
        environment.update({
            "PYTHONPATH": str(backend), "MC_ADMIN_CONFIG": str(config), "MC_ADMIN_ENV": str(config),
            "MASTER_TOKEN": "synthetic-release-token", "JWT__SECRET_KEY": "synthetic-release-key-at-least-32-bytes",
            "DATABASE_URL": f"sqlite+aiosqlite:///{database}", "SERVER_PATH": str(root / "servers"),
            "LOGS_DIR": str(root / "logs"), "ARCHIVE_PATH": str(root / "archives"),
        })
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--seed", str(database)],
                       cwd=backend, env=environment, check=True, capture_output=True, text=True)
        with closing(sqlite3.connect(database)) as connection, connection:
            sql = "\n".join(connection.iterdump()) + "\n"
            revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / f"{RELEASE}.sql").write_text(sql)
        (OUTPUT / f"{RELEASE}.json").write_text(json.dumps({
            "release": RELEASE, "commit": COMMIT, "revision": revision,
            "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
            "source": "Pinned release app.db.migrations.ensure_database_schema and models; only synthetic records",
            "generation": "uv run python tests/support/release_fixture.py",
        }, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=Path)
    arguments = parser.parse_args()
    if arguments.seed:
        seed(arguments.seed)
    else:
        generate()
