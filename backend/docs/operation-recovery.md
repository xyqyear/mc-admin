# Operation recovery and deployment ownership

Read this before changing interruption handling, explicit recovery resolution or
deployment ownership. The [journal and resource contract](operations.md) owns
acceptance, durable state and notifications; [runtime](runtime.md) owns full
startup/shutdown ordering. Recovery never replays interrupted business commands.

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

## Historical reads and recovery resolution

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
Cancellation freezes verified processes before enumerating their descendants,
then repeats discovery until every captured process is stopped. This prevents
a concurrent fork from escaping the termination set and retaining output pipes.
TERM is queued before CONT so normal shutdown handlers can run; timed-out
children receive KILL through the same handles. Failed discovery resumes the
captured processes and retains recovery evidence instead of guessing ownership.

Exit confirmation first checks the boot identity. In the matching PID namespace,
signal 0 can prove that a valid registered process group no longer exists;
only ESRCH permits skipping enumeration. Existing groups, permission errors and
uncertain results retain the detailed membership scan. Parent exit alone cannot
prove descendant termination. Actual signals still use verified pidfds, and the
persisted process identity format is unchanged.

Downgrade of `2026092501` refuses to drop the journal while protected records
remain. Rehearse migration and rollback using a disposable database copy and
retain recovery evidence before changing a deployed schema. Once only ordinary
terminal history remains, downgrade drops the journal and its history; it does
not modify server, player or snapshot data. Application rollback requires a
version verified against the retained schema and ownership semantics; preserving
an older API does not make arbitrary older application binaries safe to run.
Schedule and restoration evidence have additional revision-specific downgrade
guards, including the current name-based schedule model. See the
[schema reference](database-schema.md) before choosing a rollback target.

## Verification

Operation recovery and API tests live under `tests/operations/`. The deployed
`operations.interrupted-task-and-cron-history`, `operations.scoped-recovery-and-permissions`
and cache-degradation scenarios are documented in the
[system coverage inventory](../../e2e/docs/coverage/system.md). Use the actual
catalog for exact case IDs and select only cases affected by the change.
