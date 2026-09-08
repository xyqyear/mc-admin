from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from app.db import migrations
from tests.migrations.helpers import (
    create_unversioned_server_database,
    has_table,
    run_alembic,
    set_database_url,
    version,
)


def current_head_revision() -> str:
    head_revision = ScriptDirectory.from_config(
        migrations._alembic_config()
    ).get_current_head()
    assert head_revision is not None
    return head_revision


async def test_empty_database_is_created_and_stamped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "empty.sqlite3"
    set_database_url(monkeypatch, db_path)

    await migrations.ensure_database_schema()

    assert version(db_path) == current_head_revision()
    assert has_table(db_path, "server")
    assert has_table(db_path, "restoration")


async def test_existing_unversioned_database_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "unversioned.sqlite3"
    set_database_url(monkeypatch, db_path)

    create_unversioned_server_database(db_path)

    with pytest.raises(RuntimeError, match="not managed by Alembic"):
        await migrations.ensure_database_schema()


async def test_startup_upgrades_chat_allocation_from_previous_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "previous-head.sqlite3"
    set_database_url(monkeypatch, db_path)
    run_alembic(db_path, "upgrade", "2026060500")
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO player_chat_message VALUES (37, 1, 1, 'retained chat', '2026-09-07 00:00:00')"))
        await migrations.ensure_database_schema()
        assert version(db_path) == current_head_revision()
        with engine.begin() as connection:
            assert connection.execute(text("SELECT message_text FROM player_chat_message WHERE message_id=37")).scalar_one() == "retained chat"
            connection.execute(text("DELETE FROM player_chat_message"))
            message_id = connection.execute(text("INSERT INTO player_chat_message (player_db_id, server_db_id, message_text, sent_at) VALUES (1, 1, 'new chat', '2026-09-07 00:00:01') RETURNING message_id")).scalar_one()
            assert message_id > 37
    finally:
        engine.dispose()
