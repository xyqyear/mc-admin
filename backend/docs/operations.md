# Operation ownership and recovery

`app/operations` holds execution ownership independently of HTTP responses and
legacy task progress. The application runtime owns one journal, recovery service
and coordinator. `journal_types.py` defines the persisted contract;
`journal.py` performs short database transactions; `recovery.py` verifies stopped
writers and installs admission blocks. `processes.py` owns external process
identity and cleanup, and `execution.py` connects task, request and cron entry
points to this contract.

Manual `up`, `start`, `restart`, `stop` and `down` requests record their actor,
captured server generation and running intent under `server_<action>` operation
kinds. `daemon.py` commits unknown daemon ownership before invoking Docker and
confirms it only after the command returns successfully. Manual starts and
scheduled restarts retain their maintenance lease through failed or cancelled
execution settlement, including installation of any recovery block. Cancelling
the Docker CLI does not prove that the daemon stopped its accepted operation.
Unconfirmed scheduled execution appears as failed in legacy cron history;
cancellation with confirmed stopped writers remains cancelled. `stop` and `down`
remain available through recovery blocks, but completing either command does not
silently resolve evidence belonging to another operation.

## Durable state

Migration `2026092501` creates `operation_journal`. Acceptance commits before a
durable operation is returned to its caller. Each record carries an opaque
operation ID, actor ID, origin and legacy ID, operation kind, captured server
generation and resource scope, phase, timestamps, terminal outcome, data-change
flag, writer ownership, and recovery references. Server generations are retained
database IDs, not reusable directory names. Records deliberately have no foreign
keys that would discard evidence when a server or user is removed.

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

Metadata has additional per-record bounds: 64 resource references, 32 recovery
references, 32 owned processes, and 64 KiB per JSON collection. A global operation
should describe its global scope rather than enumerate an unbounded server list.
Bounded metadata cannot be used as a transport for arbitrary task payloads.
Old terminal rows are removed; underlying snapshots, backup repositories and
restored data are never deleted by journal retention.

## Startup recovery

The runtime acquires installation ownership and applies migrations before
recovery. DNS, scheduled work, player tracking, map workers and other producers
start only after recovery has completed. There is no automatic replay of a
previous operation.

For each active or unsettled record, recovery checks the captured generation and
writer evidence. The subprocess gate registers ownership before allowing the
child to execute. Unknown Docker mutation ownership additionally requires an
exact current generation and evidence that its container is down. A failed or
inconclusive probe remains blocked; administrator intent alone is not proof that
a writer stopped. Existing task and cron projections expose interrupted work as
failed while preserving detailed journal history.

An unresolved server write blocks conflicting writes to that generation. An
unresolved archive writer blocks its archive path. A global unresolved FILES
writer blocks conflicting server writes. Unrelated server
operations and safe reads remain available. Resolving one operation recomputes
all remaining blockers, so it cannot remove another operation's block. A record
for an old generation never applies its recovery actions or server block to a
same-name replacement.

Interrupted world/file writes invalidate the owned map tile cache. Generation
and filesystem confinement are checked before removal. Missing cache files are
already invalidated; permission errors, escaping symlinks or unknown cache
writers persist a degraded-cache flag. Cache-only failures disable the affected
cache and do not freeze unrelated server management. Live cache degradation is
persisted while the operation is active and remains sticky through finalization;
another operation's history refresh cannot erase that generation's read guard.
The recovery service's
`degraded_resources` set and `report()` expose current durable evidence. A later
successful recovery invalidation clears degradation; acknowledging partial data
does not claim that a failed cache cleanup succeeded.

Configuration recovery requires consistency verification only after a record
reports consequential changes. Validation or staging interrupted before any such
change does not force the unapplied target onto an unchanged server. For changed
configuration, recovery validates the current Minecraft Compose and accepts either
the complete recorded baseline or the intended content hash with matching source
metadata. Older records without source-hash evidence compare retained template
snapshots and values where available. Missing, ambiguous or inconsistent evidence
keeps recovery blocked. Recovery does not rewrite files, replay Docker commands or
restore the captured running intent automatically.

`configuration_stage` references identify exact temporary files beside the
canonical Compose target. Cleanup confirms stopped writers and the same server
generation, validates the recorded project-relative path and refuses redirected
parent symlinks. Records predating artifact paths use the retained project-root
token convention. Cleanup never scans by filename prefix or follows the current
Compose link to guess the old location. Terminal records with unresolved stages
remain discoverable by startup recovery, including a failed `finally` cleanup.
Failure to unlink retains the reference rather than declaring the artifact gone.

Archive publication and population similarly retain exact `archive_stage` and
`population_stage` references. Compression stages on the destination filesystem
and publishes only a completed file by atomic replacement; partial outputs do
not appear in ordinary archive listings. World previews, prune previews and
chunk restore stages retain installation-scoped artifact tokens. Their owning
feature reaps eligible artifacts after recovery, while unresolved references
preserve the corresponding directories. Cleanup neither follows an untrusted
symlink nor guesses a stage from a filename prefix.

Application finalization settles failed or cancelled execution while the lease
is still held. Unknown process ownership installs its recovery block before
waiting conflicting operations may enter. HTTP, task and finite-stream terminal
outcomes are published after the journal and required cleanup have settled.

If a live configuration operation fails or is cancelled after changing data,
its terminal record first retains a durable reconciliation block. The rebuild
keeps its maintenance lease until that one record has been checked and the
remaining admission blocks have been applied. A matching configuration clears
that block; an inconsistent or unverifiable configuration blocks conflicting
writes before waiting operations can enter. Other active operations are never
treated as interrupted by this live check. The original failed/cancelled outcome
and safe task error remain unchanged. If the backend exits during verification,
the retained block makes the record visible to startup recovery.

## History and explicit resolution API

Authenticated users can read `GET /api/operations` and
`GET /api/operations/{operation_id}`. Listing accepts `limit` from 1 to 1,000
(default 100) and a nonnegative `offset`. Responses retain actor, generation,
phase, interruption reason and recovery references without exposing process
ownership internals.

`POST /api/operations/{operation_id}/resolve` requires OWNER authority and the
normal cookie CSRF protection. Its body is:

```json
{
  "action": "acknowledge_partial",
  "resolve_references": false
}
```

Use `configuration_reconciled` for configuration work that changed data. Both
actions recheck writer termination and exact generation. Changed configuration
also requires matching baseline or intended-result evidence; unchanged work does
not need to apply its unused target. Missing records return 404; active
work, unknown writers, changed generations and inconsistent configuration return
409. Unknown fields, including `force`, are rejected.

By default, resolution records `resolved_by` and `resolved_at`, clears the
verified block, and retains unresolved references. An explicit
`resolve_references: true` marks those references resolved after the same safety
checks, making otherwise eligible history reclaimable. It does not delete the
snapshot or any referenced recovery material. Acknowledgement does not change
an interrupted operation into a successful operation.

## Supported deployment ownership

This release supports one backend writer per SQLite database and managed server
root. `SingleWriterGuard` holds kernel `flock` leases on a sidecar next to the
database and `.mc-admin-writer.lock` in the server root. Separate installations
can run concurrently; sharing either resource fails startup of a second writer.
Lock files are not unlinked because replacing a locked inode could admit two
owners. Kernel ownership is released after normal close or process exit, and
cancelled acquisition waits for its filesystem thread before releasing leases.

Use one worker and one replica on a filesystem providing consistent local
kernel locks. These leases are not a distributed multi-host coordination scheme
and do not fence external tools that directly edit managed files. SQLite
`:memory:` still acquires the server-root lease. Non-SQLite multi-writer
deployments require a separate supported ownership design.

Owned process cancellation requires Linux `pidfd_open` and `pidfd_send_signal`.
The adapter uses Python wrappers when available and libc otherwise. Unavailable
or unverifiable process handles fail cleanup and retain ownership evidence;
there is no fallback that signals a potentially reused numeric PID.

Downgrade of `2026092501` refuses to drop the journal while protected records
remain. Rehearse migration and rollback using a disposable database copy and
retain recovery evidence before changing a deployed schema. Once only ordinary
terminal history remains, downgrade drops the journal and its history; it does
not modify server, player or snapshot data. Application rollback requires a
version verified against the retained schema and ownership semantics; preserving
an older API does not make arbitrary older application binaries safe to run.
Managed schedule binding has an additional downgrade guard in `2026092502`;
restoration history has its generation-preservation guard in `2026092503`.

## Verification

`tests/operations/test_journal.py` covers transaction boundaries, immutable
terminal outcomes, capacity races, retention and bounded metadata.
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
