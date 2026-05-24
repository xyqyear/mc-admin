from pathlib import Path

from .helpers import (
    create_current_schema_downgraded_to,
    has_table,
    run_alembic,
    schema_snapshot,
    version,
)

REVISION = "f2ee81a56fee"
DOWN_REVISION = "base"


def test_upgrade_matches_current_schema_downgraded_to_f2ee(
    tmp_path: Path,
) -> None:
    expected_db_path = tmp_path / "expected-f2ee.sqlite3"
    actual_db_path = tmp_path / "actual-f2ee.sqlite3"

    create_current_schema_downgraded_to(expected_db_path, REVISION)

    assert version(expected_db_path) == REVISION
    assert not has_table(expected_db_path, "restoration")
    assert version(actual_db_path) is None

    run_alembic(actual_db_path, "upgrade", REVISION)

    assert version(actual_db_path) == REVISION
    assert not has_table(actual_db_path, "restoration")
    assert schema_snapshot(actual_db_path) == schema_snapshot(expected_db_path)

    run_alembic(actual_db_path, "downgrade", DOWN_REVISION)

    assert version(actual_db_path) is None
    assert schema_snapshot(actual_db_path) == {}
