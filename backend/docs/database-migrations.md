# Database Migrations

Application schema is managed by Alembic. FastAPI startup applies the schema
gate before any subsystem reads or writes the database.

## Startup Flow

`app.main` delegates lifespan ownership to the application runtime. After
acquiring installation writer leases, `Runtime.start()` calls
`app.db.migrations.ensure_database_schema()` before dynamic config, operation
recovery, DNS reconciliation, cron recovery and player tracking.

`ensure_database_schema()` runs synchronous Alembic work off the event loop and
uses the same configured `settings.database_url` as the async SQLAlchemy engine.
SQLite async URLs are converted from `sqlite+aiosqlite:///...` to
`sqlite:///...` for Alembic.

An in-process lock serializes Alembic environment setup across independent
application runtimes because Alembic uses process-global context proxies.
Cancellation waits for an already started migration thread before releasing the
installation writer lease. This does not permit multiple production writers.

Supported database states:

- **Empty database** — create the current SQLAlchemy metadata with
  `Base.metadata.create_all()`, then `alembic stamp head`.
- **Alembic-versioned database** — run `alembic upgrade head`.
- **Existing unversioned database** — fail startup with a clear error. This
  state requires manual intervention.

## Alembic Environment

`app.db.base` defines the shared `Base` and timezone-aware column type.
`app.db.metadata` explicitly registers tables owned by `auth`, `servers`,
`templates`, `players`, `cron`, `dynamic_config`, `self_check`, `snapshots` and
`operations`. Alembic and complete test databases import this registration
entrypoint; a feature importing its own table does not define another metadata
registry. API models live with their owning features and are separate from
database schema registration.

Moving model definitions between modules does not change table names, indexes,
column definitions, retained IDs or migration revision identifiers. OpenAPI's
existing collision-qualified component names are preserved by `app.api_schema`
so Python module organization does not rename those public references.

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

Only discardable development data may be deleted and recreated. Preserve deployed
databases and rehearse on stopped or SQLite-backed-up disposable copies. A database
whose recorded revision is outside the active graph needs an explicitly verified
migration path; changing its stamp alone does not upgrade its schema or data.

API compatibility is separate from schema compatibility. Application rollback is
supported only to a build verified against the retained schema, server generations
and operation recovery semantics. Stop admission and drain writers before changing
binaries. An arbitrary older version can misinterpret retained names or ignore
recovery blocks even when it can connect to the database. Database snapshot
restoration is a separate controlled recovery and must not overwrite subsequent
user activity automatically.

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


## Schema and repair reference

The [schema reference](database-schema.md) records revision-specific data
contracts and downgrade guards. Read the relevant section before maintenance:

- [Duplicate player sessions](database-schema.md#unique-open-player-sessions): offline preview, reviewed repair and durable evidence.
- [Server identity](database-schema.md#persistent-server-instance-identity): duplicate-name preflight and retained generations.
- [Operation journal](database-schema.md#consequential-operation-journal): protected recovery evidence.
- [Restoration bindings](database-schema.md#restoration-history-bindings) and [unified evidence](database-schema.md#unified-restoration-evidence): rollback identity and scope preservation.
- [Restart schedules](database-schema.md#name-based-restart-schedules): logical targets and schema-compatible rollback.

Detailed intermediate revisions remain in that reference because deployed
databases can still enter the migration graph there. They do not redefine
current application behavior.
