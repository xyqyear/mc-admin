from pathlib import Path

import pytest
from alembic.script import ScriptDirectory

from app.db import migrations
from tests.migrations.helpers import (
    create_unversioned_server_database,
    has_table,
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
