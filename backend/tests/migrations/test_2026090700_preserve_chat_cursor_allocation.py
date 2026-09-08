from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from .helpers import run_alembic, schema_snapshot, version

REVISION = "2026090700"
DOWN_REVISION = "2026060500"


@pytest.mark.parametrize("retained_ids", [[], [3, 41]])
def test_chat_cursor_migration_preserves_rows_indexes_and_allocation(
    tmp_path: Path, retained_ids: list[int]
) -> None:
    db_path = tmp_path / "chat-cursors.sqlite3"
    run_alembic(db_path, "upgrade", DOWN_REVISION)
    engine = create_engine(f"sqlite:///{db_path}")
    insert = text("INSERT INTO player_chat_message "
                  "(player_db_id, server_db_id, message_text, sent_at) "
                  "VALUES (7, 8, 'after cleanup', '2026-09-07 00:00:00') RETURNING message_id")
    try:
        with engine.begin() as connection:
            for message_id in retained_ids:
                connection.execute(text("INSERT INTO player_chat_message VALUES (:id, 7, 8, :message, :sent)"),
                                   {"id": message_id, "message": f"保留聊天 {message_id}", "sent": "2026-09-06 12:34:56"})
            before_rows = connection.execute(text("SELECT * FROM player_chat_message ORDER BY message_id")).all()
        before_schema = schema_snapshot(db_path)
        run_alembic(db_path, "upgrade", REVISION)
        assert version(db_path) == REVISION
        assert schema_snapshot(db_path) == before_schema
        with engine.begin() as connection:
            sql = connection.execute(text("SELECT sql FROM sqlite_master WHERE name='player_chat_message'")).scalar_one()
            assert "AUTOINCREMENT" in sql
            assert connection.execute(text("SELECT * FROM player_chat_message ORDER BY message_id")).all() == before_rows
            first = connection.execute(insert).scalar_one()
            assert first > max(retained_ids, default=0)
            connection.execute(text("DELETE FROM player_chat_message WHERE message_id=:id"), {"id": first})
            second = connection.execute(insert).scalar_one()
            assert second > first
            connection.execute(text("DELETE FROM player_chat_message"))
        engine.dispose()
        with engine.begin() as connection:
            third = connection.execute(insert).scalar_one()
            assert third > second
            rows_before_downgrade = connection.execute(text("SELECT * FROM player_chat_message")).all()
        run_alembic(db_path, "downgrade", DOWN_REVISION)
        assert version(db_path) == DOWN_REVISION
        assert schema_snapshot(db_path) == before_schema
        with engine.connect() as connection:
            sql = connection.execute(text("SELECT sql FROM sqlite_master WHERE name='player_chat_message'")).scalar_one()
            assert "AUTOINCREMENT" not in sql
            assert connection.execute(text("SELECT * FROM player_chat_message")).all() == rows_before_downgrade
    finally:
        engine.dispose()
