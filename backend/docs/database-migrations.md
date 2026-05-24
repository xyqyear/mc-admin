# Database Migrations

Application schema is managed by Alembic. FastAPI startup applies the schema
gate before any subsystem reads or writes the database.

## Startup Flow

`app.main` calls `app.db.migrations.ensure_database_schema()` at the start of
lifespan, before dynamic config, DNS reconciliation, cron recovery, player
tracking, and world-restore crash recovery.

`ensure_database_schema()` runs synchronous Alembic work off the event loop and
uses the same configured `settings.database_url` as the async SQLAlchemy engine.
SQLite async URLs are converted from `sqlite+aiosqlite:///...` to
`sqlite:///...` for Alembic.

Supported database states:

- **Empty database** — create the current SQLAlchemy metadata with
  `Base.metadata.create_all()`, then `alembic stamp head`.
- **Alembic-versioned database** — run `alembic upgrade head`.
- **Existing unversioned database** — fail startup with a clear error. This
  state requires manual intervention.

## Alembic Environment

`alembic/env.py` accepts a shared SQLAlchemy connection from
`Config.attributes["connection"]`. Programmatic startup migrations use this
path so commands run on the connection opened by `app.db.migrations`.

CLI Alembic commands still work without a shared connection; `env.py` creates
and disposes its own synchronous engine in that case.

## Revision Policy

The active migration graph starts at `f2ee81a56fee`, which is the baseline for
currently supported deployed databases. Earlier historical revisions are not
part of the active graph.

`f2ee81a56fee` is a full baseline schema snapshot through server template
support. It keeps the same revision ID as deployed databases already stamped at
that version, but fresh databases can build the complete baseline directly from
that one revision.

New revision IDs use a numeric `YYYYMMDDNN` format:

- `YYYYMMDD` is the date the revision is created.
- `NN` is a two-digit same-day sequence starting at `00`.
- Example: `2026052400`.

Create future revisions with an explicit ID:

```bash
uv run alembic revision --rev-id 2026052401 -m "add example table"
```

Do not rename a revision after it has been included in a release unless every
database stamped with the old revision is intentionally restamped or migrated.

## Operational Notes

The normal application start path runs migrations automatically. `uv run
alembic upgrade head` remains useful for manual maintenance and diagnostics,
but it is not required before launching the app.

The default local SQLite file may be deleted and recreated when it contains
discardable development data. Existing local databases stamped with a revision
that is no longer in the active graph should be restamped manually or recreated.

## Migration Tests

Each active revision has its own upgrade/downgrade test file under
`tests/migrations/`, named `test_<revision>_<description>.py`. Tests should
assert the actual table, column, or index changes introduced by the revision,
not just the Alembic version stamp.

The baseline revision test compares a fresh `alembic upgrade f2ee81a56fee`
against a temporary database built from `Base.metadata.create_all()`, stamped at
head, and downgraded to `f2ee81a56fee`. This keeps the baseline aligned with the
current model schema without touching any local development database.

`tests/migrations/test_revision_coverage.py` fails when the active Alembic
graph contains a revision without a matching test filename. Shared migration
test helpers live in `tests/migrations/helpers.py`.

Startup migration tests stay in `tests/test_startup_migrations.py` and use
`ensure_database_schema()` so the app lifespan and test path share the same
migration entry point.
