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
`templates`, `players`, `cron`, `dynamic_config`, `self_check`, `world` and
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

## Chat cursor allocation

Revision `2026090700` follows `2026060500` and recreates only
`player_chat_message` using Alembic batch reflection/copy with SQLite explicit
AUTOINCREMENT. The existing columns, row IDs, message contents, and indexes are
preserved. Fresh databases receive the same table option from SQLAlchemy
metadata. Cleanup after upgrade cannot reuse committed message IDs, including
after the message table becomes empty.

The initial allocation high-water mark is the highest retained message ID.
Previously deleted historical IDs were not recorded by the old allocator and
cannot be reconstructed during migration. Clients holding such pre-upgrade
cursors are outside this retention guarantee. Downgrading preserves remaining
rows and indexes but removes explicit AUTOINCREMENT and its non-reuse guarantee.

## Unique open player sessions

Revision `2026092400` follows `2026090700` and adds the SQLite partial unique
index `uq_player_session_open` on `(player_db_id, server_db_id)` where `left_at`
is null. Clean databases migrate without changing any row. Duplicate open
sessions fail the migration before schema or data mutation and leave the prior
revision intact. There is no automatic historical repair during startup.

The standalone `app.db.session_repair` maintenance command takes an explicit
SQLite path and never resolves the application's configured database. Stop the
application, retain a database backup, and rehearse on a disposable copy before
using the same process on a deployed database. Do not copy a live SQLite database
with ordinary file copying; use SQLite's backup mechanism or a stopped database.

```bash
uv run python -m app.db.session_repair preview \
  --database /tmp/rehearsal.sqlite3 --report /tmp/session-repair-plan.json

# Review every canonical session and proposed before/after row in the report.
uv run python -m app.db.session_repair apply \
  --database /tmp/rehearsal.sqlite3 --report /tmp/session-repair-plan.json \
  --evidence /tmp/session-repair-evidence.json
```

The policy retains the earliest `joined_at` as the single open interval, using
the lowest session ID to break timestamp ties. Redundant open rows retain their
IDs and join timestamps, but end at their own join timestamp with zero duration.
This preserves the observed interval once and keeps repaired rows inspectable.
Unrelated closed history, other player/server pairs, and historical IDs are not
rewritten. Reports carry the complete affected rows and a content fingerprint;
application requires an exact match with the current duplicate groups under a
SQLite write transaction. A stale or edited report must be regenerated and
reviewed. No hidden default database or implicit apply mode exists.

Before mutating rows, apply exclusively creates and fsyncs the `--evidence` file
with the reviewed report and `prepared` status. All row updates commit together;
database errors roll them back. After commit it exclusively creates a companion
`<evidence>.committed` file containing the same report and completion time. Keep
both as repair evidence. A prepared file alone is not proof of success: a crash
or output failure may occur before or after the database commit. Compare its
before/after rows with the stopped database before retrying, and use new output
paths for a new attempt. The tool never overwrites prior reports or evidence.

Once repair is reviewed and applied, the normal startup migration can enforce
uniqueness. Downgrade only drops this index; it neither deletes historical IDs
nor undoes approved repairs. Repair evidence remains external to the database
and survives schema rollback. Restoring a pre-repair database backup is a
separate controlled recovery and must not overwrite subsequent user activity.

## Persistent server instance identity

Revision `2026092500` follows `2026092400`. It preserves every `server` row and
ID while enabling SQLite AUTOINCREMENT and the partial unique index
`uq_server_active_name` for `status='ACTIVE'`. `Server.id` is the persistent
instance generation: deleting/deactivating a server retains a REMOVED tombstone,
and explicit recreation/adoption allocates a new ID. Fresh metadata has the same
constraints. IDs committed after this migration are not reused even if a table
is emptied manually; the initial high-water mark is the highest retained ID.
Deleted IDs absent from the pre-migration database cannot be reconstructed.

An existing duplicate ACTIVE name fails preflight before changing the schema or
history. Stop the application, retain a backup and investigate on a disposable
copy using `SELECT id, server_id, status, created_at, updated_at FROM server
WHERE server_id IN (SELECT server_id FROM server WHERE status='ACTIVE' GROUP BY
server_id HAVING COUNT(*) > 1) ORDER BY server_id, id;`. Identify the current
instance from its directory and historical references; there is no safe generic
rule that the newest row owns the data. Review and record the affected IDs
before explicitly marking non-current rows REMOVED. Do not delete rows, merge
IDs or reassign player/restoration history. If ownership remains ambiguous,
leave the migration blocked until it can be resolved. Startup never applies a
repair or adopts a directory automatically.

Downgrade preserves rows and their IDs, drops the active-name index and removes
AUTOINCREMENT. The non-reuse/uniqueness guarantee ends at that downgrade; older
code must not continue operating on references from the newer runtime.

## Consequential operation journal

Revision `2026092501` follows `2026092500` and creates `operation_journal` without
rewriting existing server, player, task or restoration rows. It persists actor,
resource generation, last phase, terminal outcome, process ownership and bounded
recovery references. Fresh database metadata imports the journal model through
`app.db.metadata`; migration and fresh-schema paths share its definition.

Downgrade refuses to delete the journal if any record is active, has an
unconfirmed writer, retains a recovery block, has unresolved recovery references
or marks a cache degraded. Resolve the actual recovery condition before retrying;
do not force-delete its evidence. Once all records are ordinary terminal
history, downgrade drops that history and its indexes without changing managed
server data. See [operation ownership and recovery](operations.md) for retention,
explicit reference resolution, startup ordering and supported single-writer
deployment constraints.

## Managed restart schedule bindings

Revision `2026092502` follows `2026092501`. It
adds nullable `CronJob.managed_server_generation`, `managed_purpose` and
`managed_binding_issue`, a complete-binding check constraint and the unique index
`uq_cronjob_managed_binding` on generation and purpose. Ordinary independent cron
jobs keep all three fields null and retain their flexible names and parameters.
The unique constraint applies to managed plans even when paused or cancelled.

Historical backfill uses exact canonical name, restart job type, matching server
parameter, creation/update timestamps and retained server lifetimes. A candidate
must fit exactly one non-overlapping generation; competing candidates for that
generation remain unassigned. Old plans can bind to their proven old generation,
but cannot bind to a same-name replacement merely because it is active. Uncertain
rows retain an issue code and null generation. Migration warnings identify the
affected job IDs, and the fields preserve the report after startup.

No pre-existing job IDs, parameters, status, counts or execution-history rows are
rewritten. SQLite starts a real database transaction before Alembic batch DDL;
constraint-installation failure rolls back both schema/backfill and temporary
table creation, allowing a direct retry. Tests exercise mixed valid/ambiguous
history, same-name generations, integrity constraints, failed upgrade and retry,
and equivalence with fresh metadata.

Inspect the report on a disposable database copy and use the cron detail API to
review retained jobs. Unresolved non-cancelled candidates return 409 from affected
server-plan operations and do not run automatically. Explicitly cancelling a
reviewed ambiguous plan preserves its evidence and allows creating a fresh managed
plan for the current server. See [cron](cron.md) for the exact rules and report query.

Downgrade below `2026092502` refuses to remove the binding fields while any managed
binding or ambiguity report remains, regardless of task status. Losing that
identity protection would allow older name-based code to reinterpret history.
An empty-binding database can downgrade without changing independent jobs. Do not
erase binding evidence to force a production rollback; use a schema-compatible
application build or a separately reviewed database recovery.

## Restoration history bindings

Revision `2026092503` follows `2026092502` and is the current migration head.
It adds nullable `Restoration.server_generation` and `binding_issue`. Every
existing restoration ID, status, snapshot reference and selection JSON remains
unchanged. Backfill binds a row only when its recorded interval belongs to one
unambiguous retained server lifetime. Missing servers, overlapping lifetimes or
insufficient timestamps retain an issue instead of choosing the current server.
History stays readable; rollback returns `restoration_identity_conflict` when
the bound generation is absent, uncertain or differs from the current instance.

New restorations capture a resolved `ServerRef` and revalidate it under the
execution lease. A rollback repeats that validation after request admission, so
same-name replacement cannot redirect a previously accepted operation. SQLite
batch DDL runs in a real transaction. Migration tests compare fresh metadata,
preserve history and cover ambiguous lifetimes and empty databases.

Downgrade below `2026092503` refuses to remove identity fields while restoration
rows exist. An empty restoration table can downgrade. Use a schema-compatible
application build for an installation with retained history; deleting recovery
history is not a rollback procedure.
