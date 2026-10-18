# Database schema and compatibility reference

This reference records retained data, identity guarantees and downgrade guards
for supported revisions. [Migration operations](database-migrations.md) explains
startup, revision authoring and validation; [deployment rehearsal](../../e2e/docs/deployment-rehearsal.md)
owns released-image upgrade and checkpoint exercises. Commands below run from
`backend/` and require the explicitly described stopped, disposable database.

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

## Historical managed restart schedule bindings

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

These fields belong to this intermediate schema revision. The current head
removes instance bindings through `2026100700`; retained valid plans resolve their
target by the configured server name. See [cron](cron.md) for current selection
and execution rules.

Downgrade below `2026092502` refuses to remove the binding fields while any managed
binding or ambiguity report remains, regardless of task status. Losing that
identity protection would allow older name-based code to reinterpret history.
An empty-binding database can downgrade without changing independent jobs. Do not
erase binding evidence to force a production rollback; use a schema-compatible
application build or a separately reviewed database recovery.

## Restoration history bindings

Revision `2026092503` follows `2026092502`.
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

## Unified restoration evidence

Revision `2026093000` follows `2026092503`. The physical `restoration`
table keeps its IDs and all historical evidence. Its model, selection contracts,
store and startup reconciliation belong to `app.snapshots`. Nullable versioned
scope, target generations, protection rules, operation ID, entry point and rollback
parent fields support common recovery commands. A global record can have no
single `server_id`; `targets_json` holds its explicit identities.

Existing world rows receive a version 1 scope and their already recorded target
generation. Migration never guesses operation IDs, rollback parents or missing
generations. Original selection JSON, absence markers, binding issues, timestamps
and snapshot references remain unchanged. Startup interrupts pending and running
records without replaying writes. Migration tests seed the previous revision,
verify retained data through both SQLite and the application store, compare
fresh metadata, and check operation ID uniqueness.

Downgrade below `2026093000` refuses while any restoration history remains. Use a
schema-compatible application build or a separately reviewed database recovery;
do not discard safety evidence to force an older application to start.

## Retained task results

Revision `2026100100` adds nullable
`operation_journal.task_result_json` without changing existing operation history.
Legacy rows have no payload; new task results survive list dismissal and backend
restart for the journal retention period. The ORM defers this column so list and
recovery queries do not load large results. Downgrade removes the payload column
and its contents while preserving operation metadata and recovery evidence.

## Snapshot notes

Revision `2026100600` follows `2026100100`.
It adds `snapshot_notes`, keyed by actual Restic repository config ID and complete
snapshot ID. A check constraint limits note text to 500 Unicode characters.
Historical snapshots project an empty note without a database backfill. Existing
restoration references, retained task results and repository content remain intact.
Downgrade removes notes while preserving those existing tables and their evidence.

## Name-based restart schedules

Revision `2026100700` follows `2026100600`.
It removes `cronjob.managed_server_generation`, `managed_binding_issue`,
`uq_cronjob_managed_binding` and `ck_cronjob_managed_binding`. The retained
`managed_purpose` distinguishes server-managed schedules from independent jobs.
Job IDs, names, parameters, desired status, execution counts and history remain
unchanged, including multiple historical plans for one server name. Valid active
plans can register without interpreting their display name or creation time as
instance evidence. Paused and cancelled plans keep their desired state.

SQLite begins a real transaction before dropping the index and replacing the
table. A failed replacement rolls back the schema and rows and permits retry.
Tests compare retained data, current metadata, integrity and downgrade boundaries.

Downgrade to `2026100600` is refused while any managed plan exists; the logical
target does not prove a historical instance binding. With no managed plans, the
old nullable columns, index and check constraint can be restored without changing
independent jobs. A production rollback must use a schema-compatible build or a
separately reviewed database recovery.

## Retained authored task failures

Revision `2026101800` is the current migration head and follows `2026100700`.
It adds nullable `operation_journal.failure_message` for safe authored failures,
limited by the journal to 4096 UTF-8 bytes. Legacy rows remain null. Unknown
exception values are not retained. Upgrade preserves operation outcomes, results,
ownership and recovery evidence. Downgrade removes this presentation column and
its messages while preserving the existing journal data and recovery protections.
