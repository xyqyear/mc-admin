# Operation ownership and recovery

`app/operations` holds execution ownership independently of HTTP responses and
legacy task progress. The application runtime owns one journal, recovery service
and coordinator. `journal_types.py` defines the persisted contract;
`journal.py` performs short database transactions; `recovery.py` verifies stopped
writers and installs admission blocks. `processes.py` owns external process
identity and cleanup, and `execution.py` connects task, request and cron entry
points to this contract.

Manual `up`, `start`, `restart`, `stop` and `down` tasks record their actor,
captured server generation and running intent under `server_<action>` operation
kinds with origin `task`. Acceptance returns 202; task and operation IDs are the
same. `daemon.py` commits unknown daemon ownership before invoking Docker and
confirms it only after the command returns successfully. Manual starts and
scheduled restarts retain their maintenance lease through failed or cancelled
execution settlement, including installation of any recovery block. Cancelling
the Docker CLI does not prove that the daemon stopped its accepted operation.
Unconfirmed scheduled execution appears as failed in legacy cron history;
cancellation with confirmed stopped writers remains cancelled. `stop` and `down`
remain available through recovery blocks, but completing either command does not
silently resolve evidence belonging to another operation.

Task submission reserves conflicting lifecycle commands before journal I/O.
Creation records a prospective directory and binds the committed server generation
before continuing. Synchronization captures existing generations even when their
directories are absent and revalidates them before deactivation. Removal drains
other writers while excluding only its own task identity. See
[non-snapshot operations](non-snapshot-operations.md) for the task/API inventory.

## Durable state

Migration `2026092501` creates `operation_journal`. Acceptance commits before a
durable operation is returned to its caller. Each record carries an opaque
operation ID, actor ID, origin and legacy ID, operation kind, captured server
generation and resource scope, phase, timestamps, terminal outcome, data-change
flag, writer ownership, and recovery references. Server generations are retained
database IDs, not reusable directory names. Records deliberately have no foreign
keys that would discard evidence when a server or user is removed.

Request and background-task entrypoints retain a receipt of their own successful
acceptance before cancellation can interrupt the handoff to execution. If the
handoff fails, they settle that accepted record without starting external work;
a rejected duplicate ID cannot settle another operation. Rejection by the task
manager closes the unsubmitted generator and settles its record even if closure
fails. The original rejection and cleanup failure remain distinguishable.

File, population, archive, backup, world restore, prune and live map operations
declare their actual resource scopes before execution. FILES claims include
lexical paths and canonical symlink targets; ARCHIVE claims identify the exact
published path; MAP_CACHE claims identify the affected cache subtree. Cache
writers also claim their filesystem output paths. Nested safety snapshots reuse
an explicitly validated parent lease, and never acquire a broader scope while
holding a narrower one. All required resources are reserved atomically.

A global FILES claim covers the server root, including future servers; creation
and adoption take their destination FILES and port claims together. This closes
the gap between global backup target discovery and concurrent server creation.
Independent paths and server generations remain concurrent. More than 64
same-server journal paths collapse to their common ancestor for bounded recovery
evidence; live execution leases retain the exact declared paths.

The journal does not store request bodies, provider credentials, environment
variables, command lines, stderr, configuration contents or raw progress events.
Failure codes and phases are bounded identifiers. Process ownership contains
only PID, process group, kernel start ticks, boot ID, and process root device and
inode. The public history omits these process details. Resource paths remain
relative and confined; Linux backslashes are literal filename characters.

Configuration operations retain an intended content hash, a baseline version
and source-metadata hash without retaining the underlying values. Owned staging
artifacts append a bounded resource path under an already declared server and
generation. Artifact registration cannot extend the operation to a new server.

The phase is preserved when an operation becomes interrupted. `data_changed`
remains true once any stage reports a consequential write. Successful, cancelled
and skipped terminal states require confirmed stopped writers. A terminal
outcome cannot be overwritten by late progress or a second completion attempt.
Recovery may update ownership evidence and resolution metadata without rewriting
the original terminal outcome.

The default retention policy admits at most 10,000 records and expires ordinary
terminal history after 30 days. Admission and pruning share a SQLite
`BEGIN IMMEDIATE` transaction, including when separate journal objects use the
same database. Active records, unconfirmed writers, blocked recovery, degraded
caches and unresolved recovery references are never evicted. When protected
records fill capacity, new admission returns a safe 503 response. The journal
does not silently discard safety evidence to make room.

Each short journal call owns its database task through cursor consumption,
commit or rollback, and session closure. Cancellation waits for that task to
settle before releasing the write mutex and propagating to the caller. Read
queries use the same lifetime boundary because an unfinished SQLite cursor can
also block writes. Waiting for the mutex remains cancellable, and cancellation
is checked before starting a database call and before returning to external
work. This boundary contains metadata operations only; it does not shield
filesystem changes, subprocesses or the rest of a cancelled request.

Metadata has additional per-record bounds: 64 resource references, 32 recovery
references, 32 owned processes, and 64 KiB per JSON collection. A global operation
should describe its global scope rather than enumerate an unbounded server list.
Bounded metadata cannot be used as a transport for arbitrary task payloads.
Feature results use the separate nullable `task_result_json` column. Task workers
save it before exposing results; the ORM defers it for metadata, list and recovery
reads. Task details load it, including for dismissed or restarted tasks;
already-loaded settled results up to 16 KiB can also accompany task events.
Structured progress does not load or rewrite journal results.
Old terminal rows are removed; underlying snapshots, backup repositories and
restored data are never deleted by journal retention.

## Startup recovery

Recovery verifies captured generations and stopped-writer evidence before
producers start. Unknown writers retain resource blocks; interrupted commands
are not replayed. Lifecycle, configuration, artifact and cache settlement, along
with supported deployment ownership, are defined in [operation recovery](operation-recovery.md).

## History and explicit resolution API

### Incremental cache refresh

The runtime-owned journal owns one in-memory `OperationChangeFeed`; applications
never share queues or per-client read positions. Successful short transactions
capture immutable metadata and publish synchronously after commit, before
session closure or an acceptance callback. Acceptance, terminal outcomes,
resource/data changes and effective terminal recovery changes notify. Routine
phase, process ownership and task-result updates do not. Failed transactions
emit nothing. Notification failure resets the feed identity without changing
committed business results, and active tracking still reflects committed states.

Authenticated `GET /api/operations/changes` accepts an opaque `cursor` and a
`limit` from 1 to 1,000, defaulting to 200. It returns `items`, `next_cursor`,
`has_more`, `active_count` and `reset_required`. Each item contains only
`sequence`, `operation_id`, `kind`, `state`, `data_changed`, `updated_at`,
`ended_at` and `resources`. Reads do not query the database or load complete
history. Task presentation continues using task and feature APIs.

The cursor binds a random per-instance identity to a strictly increasing
notification sequence. Paged responses pin their initial upper sequence; new
commits become visible in the following batch. Every continuation checks the
retention boundary. Missing, malformed, future, different-instance or expired
cursors return empty items, `reset_required: true` and a current-head cursor.
Clients refresh relevant authoritative queries and map image versions, then
consume changes after that cursor, including commits made during refresh.

The feed retains at most 2,000 items and 4 MiB of serialized notification data.
Python container overhead is additionally bounded by item and journal metadata
limits. Oldest entries are removed when either limit is reached. An individually
oversized notification advances the discarded boundary and clears retained
items, forcing existing readers to resynchronize. Neither notification eviction
nor restart deletes journal evidence, task results or managed data.

Only nonterminal operation IDs are retained for active counting, bounded by
journal admission capacity. Startup initializes them from persisted nonterminal
rows before recovery; committed acceptance and completion update the set. Runtime
shutdown clears the feed after writers have stopped. Browsers retain their own
processed cursor and process bounded batches. `/api/tasks/events` accepts
`operation_cursor` and sends `operation_changes` frames from the same ring;
synchronous listeners only wake subscriptions after commit. Each open subscription
retains its read position and dirty flag, with no duplicate history queue or
periodic database read. Retention gaps and instance changes use the same explicit
reset contract. Disconnect and shutdown remove wake listeners.

### Historical reads and recovery resolution

Authenticated history reads retain actor, generation and bounded recovery
evidence. OWNER-only resolution rechecks writer termination and consistency;
acknowledging partial work does not turn it into success. The
[history and resolution API](operation-recovery.md#historical-reads-and-recovery-resolution)
documents parameters, conflicts and retained references.

## Supported deployment ownership

One writer owns each database and server root. Linux process identity and
filesystem locks are part of this deployment contract; see
[supported ownership](operation-recovery.md#supported-deployment-ownership) before
changing worker count, recovery cleanup or application/schema rollback.

## Verification

`tests/operations/test_journal.py` covers transaction boundaries, immutable
terminal outcomes, capacity races, retention and bounded metadata.
`test_changes.py` covers post-commit visibility, rollback, bounded notification
retention, pinned pagination, instance resets, active counting and notification
failure recovery. `test_api.py` checks authenticated lightweight reads without
journal database polling; the two-application runtime case checks feed isolation
and shutdown clears retained notifications after draining writers.
`test_journal_cancellation.py` interrupts real file-backed SQLite calls after
their worker has executed a statement, retains the cancellation traceback, and
verifies writes through an independent connection. It also checks repeated
cancellation during session closure and cancellation while waiting for the
mutex. The API scenario `world.safety-snapshot-disconnect` disconnects task observation after safety evidence and pauses the real Restic writer. Reconnection observes the same task/operation completing; unrelated management writes and a later byte-checked safety rollback verify retained recovery data. Explicit cancellation and process interruption have separate scenarios.
`test_recovery.py` covers interruption without replay, ownership uncertainty,
global and per-server blocks, generation reuse, actual cache confinement and
configuration-source equality. `test_single_writer.py` exercises concurrent
installations, an owned child process killed while holding leases, and cancelled
acquisition. `test_api.py` uses actual cookie authentication and CSRF middleware
to verify history visibility and owner-only resolution. Migration tests preserve
historical rows, compare fresh journal metadata and refuse unsafe downgrade.
`tests/configuration/` checks staged file ownership, cancellation during filesystem
work, source-commit failure and validation-only interruption. See
[configuration application](configuration.md) for the phase order and external
filesystem race boundary.
