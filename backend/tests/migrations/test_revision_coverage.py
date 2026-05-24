from pathlib import Path

from alembic.script import ScriptDirectory

from app.db import migrations


def test_all_active_migration_revisions_have_schema_tests() -> None:
    script = ScriptDirectory.from_config(migrations._alembic_config())
    active_revisions: set[str] = set()
    for revision in script.walk_revisions(base="base"):
        if revision.revision is not None:
            active_revisions.add(revision.revision)

    migration_test_revisions = {
        path.name.removeprefix("test_").split("_", 1)[0]
        for path in Path(__file__).parent.glob("test_*.py")
        if path.name != "test_revision_coverage.py"
    }

    assert active_revisions == migration_test_revisions
