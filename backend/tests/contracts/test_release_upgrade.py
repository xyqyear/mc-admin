import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from alembic.script import ScriptDirectory
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db import migrations
from app.main import api_app
from tests.support.runtime import set_runtime_resource

FIXTURES = Path(__file__).parent / "fixtures/releases"


async def test_supported_release_upgrade_preserves_synthetic_history(tmp_path, monkeypatch):
    sql = (FIXTURES / "v5.3.0.sql").read_bytes()
    provenance = json.loads((FIXTURES / "v5.3.0.json").read_text())
    assert hashlib.sha256(sql).hexdigest() == provenance["sql_sha256"]
    db_path = tmp_path / "released.sqlite3"
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.executescript(sql.decode())
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == provenance["revision"]
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
        )]
        retained = {
            table: ([row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')],
                    connection.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall())
            for table in tables
        }
    monkeypatch.setattr(get_settings(), "database_url", f"sqlite+aiosqlite:///{db_path}")
    await migrations.ensure_database_schema()
    await migrations.ensure_database_schema()
    with closing(sqlite3.connect(db_path)) as connection, connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == ScriptDirectory.from_config(migrations._alembic_config()).get_current_head()
        for table, (columns, records) in retained.items():
            projection = ",".join(f'"{column}"' for column in columns)
            assert connection.execute(f'SELECT {projection} FROM "{table}" ORDER BY 1').fetchall() == records, table
        connection.execute("DELETE FROM player_chat_message")
        identity = connection.execute(
            "INSERT INTO player_chat_message (player_db_id,server_db_id,message_text,sent_at) VALUES (301,101,'Synthetic new chat','2026-09-01 00:01:00') RETURNING message_id"
        ).fetchone()[0]
        assert identity > 501
    engine = create_async_engine(get_settings().database_url)
    set_runtime_resource(monkeypatch, 'session_factory', async_sessionmaker(engine, expire_on_commit=False))
    try:
        async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test",
                               headers={"Authorization": f"Bearer {get_settings().master_token}"}) as client:
            users = await client.get("/admin/users")
            assert users.status_code == 200
            assert users.json()[0]["username"] == "synthetic-owner"
            assert "hashed_password" not in users.json()[0]
            templates = await client.get("/templates/")
            assert templates.status_code == 200
            assert templates.json()[0]["id"] == 201
    finally:
        await engine.dispose()
